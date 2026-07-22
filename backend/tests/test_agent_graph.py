from collections import deque
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import pytest
import pytest_asyncio
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.agent.graph import build_agent_graph
from loregraph.agent.state import AgentState
from loregraph.llm.structured import StructuredResult
from loregraph.llm.usage import LLMCallUsage
from loregraph.schemas.agent import (
    DraftEntity,
    DraftRelationship,
    GroundingReport,
    LoreDraft,
)
from loregraph.schemas.entity import EntityCreate
from loregraph.schemas.project import ProjectCreate
from loregraph.services.edge_service import EdgeService
from loregraph.services.entity_service import EntityService
from loregraph.services.vector_index import VectorIndex
from loregraph.storage.sqlite.db import (
    create_engine_for,
    init_db,
    make_session_factory,
)
from loregraph.storage.sqlite.edge_store import SqliteEdgeStore
from loregraph.storage.sqlite.entity_store import SqliteEntityStore
from loregraph.storage.sqlite.project_store import SqliteProjectStore
from loregraph.storage.sqlite.usage_store import SqliteUsageStore
from tests.fakes import FixedVectorIndex


class ScriptedChatModel(BaseChatModel):
    """Returns pre-scripted AIMessages in order; ignores bound tools (the
    script decides when to 'call' one via AIMessage.tool_calls)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    script: deque[AIMessage]

    def bind_tools(self, tools: Any, **kwargs: Any) -> Runnable[Any, Any]:
        return self

    def _generate(
        self,
        messages: Any,
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        message = self.script.popleft()
        return ChatResult(generations=[ChatGeneration(message=message)])

    @property
    def _llm_type(self) -> str:
        return "scripted"


class FakeGenerator:
    """Returns canned structured outputs in order; asserts schema match."""

    def __init__(self, results: list[BaseModel]) -> None:
        self._results = deque(results)

    async def generate[T: BaseModel](
        self, schema: type[T], *, system: str, user: str, cached_prefix: str = ""
    ) -> StructuredResult[T]:
        value = self._results.popleft()
        assert isinstance(value, schema), f"expected {schema}, got {type(value)}"
        return StructuredResult(value, LLMCallUsage(input_tokens=100, output_tokens=50))


@pytest_asyncio.fixture
async def db_session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    engine = create_engine_for(tmp_path / "test.sqlite3")
    await init_db(engine)
    session = make_session_factory(engine)()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()


def make_graph(
    session: AsyncSession,
    script: list[AIMessage],
    creative_results: list[BaseModel] | None = None,
    extraction_results: list[BaseModel] | None = None,
    retrieved_entity_ids: list[str] | None = None,
) -> Any:
    entity_store = SqliteEntityStore(session)
    edge_store = SqliteEdgeStore(session)
    return build_agent_graph(
        chat_model=ScriptedChatModel(script=deque(script)),
        creative=FakeGenerator(creative_results or []),
        extraction=FakeGenerator(extraction_results or []),
        vector_index=(
            cast(VectorIndex, FixedVectorIndex(retrieved_entity_ids))
            if retrieved_entity_ids is not None
            else None
        ),
        knowledge_index=None,
        entity_store=entity_store,
        edge_store=edge_store,
        project_store=SqliteProjectStore(session),
        entity_service=EntityService(entity_store),
        edge_service=EdgeService(edge_store, entity_store),
        token_budget=100_000,
        checkpointer=MemorySaver(),
    )


CONFIG: RunnableConfig = {"configurable": {"thread_id": "t1"}}


def turn(project_id: str, text: str) -> dict[str, Any]:
    return {"project_id": project_id, "messages": [HumanMessage(text)]}


def propose_call(brief: str) -> AIMessage:
    return AIMessage(
        "",
        tool_calls=[{"name": "propose_lore", "args": {"brief": brief}, "id": "tc1"}],
    )


def starter_lore() -> LoreDraft:
    return LoreDraft(
        entities=[
            DraftEntity(
                ref="e1", type="location", title="Норвинтер", summary="Портовый город."
            ),
            DraftEntity(
                ref="e2", type="npc", title="Мира Кузнец", summary="Мастер-кузнец."
            ),
        ],
        relationships=[
            DraftRelationship(
                source_ref="e2", target_ref="e1", type="located_in", reason="живёт"
            ),
        ],
    )


async def state_of(graph: Any) -> AgentState:
    return AgentState.model_validate((await graph.aget_state(CONFIG)).values)


@pytest.mark.asyncio
async def test_plain_answer_ends_turn(db_session: AsyncSession) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    graph = make_graph(db_session, [AIMessage("Городом правит гильдия.")])
    await graph.ainvoke(turn(project.id, "Кто правит городом?"), CONFIG)
    state = await state_of(graph)
    assert isinstance(state.messages[-1], AIMessage)
    assert "гильдия" in str(state.messages[-1].content)
    assert state.draft is None  # no proposal was started


@pytest.mark.asyncio
async def test_search_tool_grounds_the_answer(db_session: AsyncSession) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    entity_store = SqliteEntityStore(db_session)
    await entity_store.create(
        EntityCreate(type="npc", title="Мира Кузнец", fields=[]), project.id
    )
    graph = make_graph(
        db_session,
        [
            AIMessage(
                "",
                tool_calls=[
                    {"name": "search_lore", "args": {"query": "кузнец"}, "id": "s1"}
                ],
            ),
            AIMessage("Кузнеца зовут Мира Кузнец."),
        ],
    )
    await graph.ainvoke(turn(project.id, "Как зовут кузнеца?"), CONFIG)
    state = await state_of(graph)
    # The tool result (title-substring fallback without a vector index)
    # reached the model, and the final answer closed the turn.
    tool_texts = [str(m.content) for m in state.messages if m.type == "tool"]
    assert any("Мира Кузнец" in text for text in tool_texts)
    assert "Мира" in str(state.messages[-1].content)


@pytest.mark.asyncio
async def test_propose_interrupts_then_commit_acks_in_chat(
    db_session: AsyncSession,
) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    graph = make_graph(
        db_session,
        [propose_call("стартовый лор северного города")],
        creative_results=[starter_lore()],
    )
    await graph.ainvoke(turn(project.id, "Создай стартовый лор"), CONFIG)
    snapshot = await graph.aget_state(CONFIG)
    assert any(task.interrupts for task in snapshot.tasks)  # review gate

    await graph.ainvoke(Command(resume={"action": "approve"}), CONFIG)
    state = await state_of(graph)
    assert len(state.committed_entity_ids) == 2
    assert state.draft is None and state.draft_committed
    # Deterministic ack message, zero extra LLM tokens.
    assert "Норвинтер" in str(state.messages[-1].content)

    entities = await SqliteEntityStore(db_session).list_entities(project.id)
    assert {e.title for e in entities} == {"Норвинтер", "Мира Кузнец"}
    edges = await SqliteEdgeStore(db_session).list_all(project.id)
    assert [e.type for e in edges] == ["located_in"]


@pytest.mark.asyncio
async def test_revise_regenerates_and_reviews_again(
    db_session: AsyncSession,
) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    second = starter_lore()
    second.entities[1].title = "Торвальд Молот"
    graph = make_graph(
        db_session,
        [propose_call("стартовый лор")],
        creative_results=[starter_lore(), second],
    )
    await graph.ainvoke(turn(project.id, "Создай лор"), CONFIG)

    # DM asks for changes instead of approving.
    await graph.ainvoke(
        Command(resume={"action": "revise", "feedback": "замени кузнеца на воина"}),
        CONFIG,
    )
    snapshot = await graph.aget_state(CONFIG)
    assert any(task.interrupts for task in snapshot.tasks)  # review gate again
    state = await state_of(graph)
    assert state.draft is not None
    assert {e.title for e in state.draft.entities} == {"Норвинтер", "Торвальд Молот"}

    await graph.ainvoke(Command(resume={"action": "approve"}), CONFIG)
    entities = await SqliteEntityStore(db_session).list_entities(project.id)
    assert {e.title for e in entities} == {"Норвинтер", "Торвальд Молот"}


@pytest.mark.asyncio
async def test_reject_commits_nothing_and_acks(db_session: AsyncSession) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    graph = make_graph(
        db_session,
        [propose_call("стартовый лор")],
        creative_results=[starter_lore()],
    )
    await graph.ainvoke(turn(project.id, "Создай лор"), CONFIG)
    await graph.ainvoke(Command(resume={"action": "reject"}), CONFIG)

    assert await SqliteEntityStore(db_session).list_entities(project.id) == []
    state = await state_of(graph)
    assert state.committed_entity_ids == []
    last_message = state.messages[-1]
    assert (
        last_message.additional_kwargs.get("event", {}).get("code") == "batch_rejected"
    )


@pytest.mark.asyncio
async def test_budget_exhaustion_mid_retry_reaches_review(
    db_session: AsyncSession,
) -> None:
    """Regression: budget running out between dedup retries must break the
    retry loop and surface the draft at review — not spin into
    GraphRecursionError (retry_feedback used to survive the early return)."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    entity_store = SqliteEntityStore(db_session)
    await entity_store.create(
        EntityCreate(type="npc", title="Мира Кузнец", fields=[]), project.id
    )
    edge_store = SqliteEdgeStore(db_session)
    graph: Any = build_agent_graph(
        chat_model=ScriptedChatModel(script=deque([propose_call("лор")])),
        # First (and only) generation collides with the existing title; the
        # FakeGenerator charges 150 tokens > the 100-token budget below.
        creative=FakeGenerator([starter_lore()]),
        extraction=FakeGenerator([]),
        vector_index=None,
        knowledge_index=None,
        entity_store=entity_store,
        edge_store=edge_store,
        project_store=SqliteProjectStore(db_session),
        entity_service=EntityService(entity_store),
        edge_service=EdgeService(edge_store, entity_store),
        token_budget=100,
        checkpointer=MemorySaver(),
    )
    await graph.ainvoke(turn(project.id, "Создай лор"), CONFIG)
    snapshot = await graph.aget_state(CONFIG)
    assert any(task.interrupts for task in snapshot.tasks)  # reached review
    state = await state_of(graph)
    assert state.retry_feedback == ""
    assert any(warning.code == "budget_exhausted" for warning in state.warnings)


@pytest.mark.asyncio
async def test_mid_batch_failure_rolls_back_created_entities(
    db_session: AsyncSession,
) -> None:
    """Regression: a failure on entity #2 must not leave entity #1 orphaned
    in the world (per-create autocommit has no surrounding transaction)."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    entity_store = SqliteEntityStore(db_session)
    edge_store = SqliteEdgeStore(db_session)

    class FailingEntityService(EntityService):
        calls = 0

        async def create(self, data: EntityCreate, project_id: str) -> Any:
            FailingEntityService.calls += 1
            if FailingEntityService.calls >= 2:
                raise RuntimeError("boom on second entity")
            return await super().create(data, project_id)

    graph: Any = build_agent_graph(
        chat_model=ScriptedChatModel(script=deque([propose_call("лор")])),
        creative=FakeGenerator([starter_lore()]),
        extraction=FakeGenerator([]),
        vector_index=None,
        knowledge_index=None,
        entity_store=entity_store,
        edge_store=edge_store,
        project_store=SqliteProjectStore(db_session),
        entity_service=FailingEntityService(entity_store),
        edge_service=EdgeService(edge_store, entity_store),
        token_budget=100_000,
        checkpointer=MemorySaver(),
    )
    await graph.ainvoke(turn(project.id, "Создай лор"), CONFIG)
    with pytest.raises(RuntimeError, match="boom"):
        await graph.ainvoke(Command(resume={"action": "approve"}), CONFIG)
    # The first (successfully created) entity was compensated away.
    assert await entity_store.list_entities(project.id) == []


@pytest.mark.asyncio
async def test_usage_is_recorded_per_node_and_model(db_session: AsyncSession) -> None:
    """End-to-end wiring: every LLM node writes its own usage row, tagged with
    the model actually behind its injected client — that is what makes the
    project rollup sliceable by node and by model."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    usage_store = SqliteUsageStore(db_session)
    entity_store = SqliteEntityStore(db_session)
    edge_store = SqliteEdgeStore(db_session)
    graph: Any = build_agent_graph(
        chat_model=ScriptedChatModel(script=deque([propose_call("лор")])),
        creative=FakeGenerator([starter_lore()]),
        extraction=FakeGenerator([]),
        vector_index=None,
        knowledge_index=None,
        entity_store=entity_store,
        edge_store=edge_store,
        project_store=SqliteProjectStore(db_session),
        entity_service=EntityService(entity_store),
        edge_service=EdgeService(edge_store, entity_store),
        token_budget=100_000,
        checkpointer=MemorySaver(),
        usage_store=usage_store,
        assistant_model_name="assistant-model",
        generation_model_name="generation-model",
        extraction_model_name="extraction-model",
    )
    await graph.ainvoke(turn(project.id, "Создай лор"), CONFIG)

    rows = {row.node: row for row in await usage_store.project_rollup(project.id)}

    assert rows["generate_lore"].model == "generation-model"
    assert rows["generate_lore"].calls == 1
    assert rows["generate_lore"].input_tokens == 100
    assert rows["generate_lore"].output_tokens == 50
    assert rows["assistant"].model == "assistant-model"
    # No lore to check against, so the grounding judge never ran — and an
    # LLM call that did not happen must not show up as spend.
    assert "verify_grounding" not in rows


def test_mentions_uses_word_boundaries() -> None:
    from loregraph.agent.nodes.check_duplicates import _mentions

    assert _mentions("расскажи про Миру и «Мира» тоже", "Мира")
    assert not _mentions("создай 1230 стражников", "123")  # no bare substring
    assert not _mentions("мирами правят боги", "Мира")  # inside a longer word
    assert not _mentions("любой текст с al внутри", "Al")  # too short


@pytest.mark.asyncio
async def test_dm_edits_win_at_approve(db_session: AsyncSession) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    graph = make_graph(
        db_session,
        [propose_call("стартовый лор")],
        creative_results=[starter_lore()],
    )
    await graph.ainvoke(turn(project.id, "Создай лор"), CONFIG)

    edited = starter_lore()
    edited.entities = [e for e in edited.entities if e.ref != "e2"]  # drop the NPC
    edited.relationships = []
    await graph.ainvoke(
        Command(resume={"action": "approve", "draft": edited.model_dump()}), CONFIG
    )
    entities = await SqliteEntityStore(db_session).list_entities(project.id)
    assert [e.title for e in entities] == ["Норвинтер"]


@pytest.mark.asyncio
async def test_propose_lore_may_connect_two_existing_entities(
    db_session: AsyncSession,
) -> None:
    """The creative pipeline is subject to the same endpoint symmetry as the
    relationship one: a proposal that links two entities already in the world
    used to be dropped by verify_grounding as an "unknown source"."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    store = SqliteEntityStore(db_session)
    mira = await store.create(
        EntityCreate(type="npc", title="Мира", fields=[]), project.id
    )
    guild = await store.create(
        EntityCreate(type="faction", title="Гильдия", fields=[]), project.id
    )

    draft = LoreDraft(
        relationships=[
            DraftRelationship(
                source_ref=mira.id,
                target_ref=guild.id,
                type="member_of",
                reason="Мира вступила в гильдию.",
            )
        ]
    )
    graph = make_graph(
        db_session,
        [propose_call("свяжи Миру с гильдией")],
        creative_results=[draft],
        # Retrieval now returns lore, so verify_grounding's LLM-as-judge tier
        # runs too — it has nothing to flag here.
        extraction_results=[
            GroundingReport(claims_checked=0, claims_flagged=0, warnings=[])
        ],
        retrieved_entity_ids=[mira.id, guild.id],
    )
    await graph.ainvoke(turn(project.id, "свяжи Миру с гильдией"), CONFIG)

    state = AgentState.model_validate((await graph.aget_state(CONFIG)).values)
    assert state.draft is not None
    assert len(state.draft.relationships) == 1, (
        "a relationship between two existing entities must survive the guard"
    )


@pytest.mark.asyncio
async def test_relationship_only_commit_acks_without_entity_counts(
    db_session: AsyncSession,
) -> None:
    """ "Committed 0 entities" reads like a failure when nothing was meant to
    be created — a rewiring gets its own acknowledgement."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    store = SqliteEntityStore(db_session)
    a = await store.create(EntityCreate(type="npc", title="A", fields=[]), project.id)
    b = await store.create(EntityCreate(type="npc", title="B", fields=[]), project.id)

    draft = LoreDraft(
        relationships=[
            DraftRelationship(source_ref=a.id, target_ref=b.id, type="ally_of")
        ]
    )
    graph = make_graph(
        db_session,
        [propose_call("свяжи их")],
        creative_results=[draft],
        # Retrieval now returns lore, so verify_grounding's LLM-as-judge tier
        # runs too — it has nothing to flag here.
        extraction_results=[
            GroundingReport(claims_checked=0, claims_flagged=0, warnings=[])
        ],
        retrieved_entity_ids=[a.id, b.id],
    )
    await graph.ainvoke(turn(project.id, "свяжи их"), CONFIG)
    await graph.ainvoke(Command(resume={"action": "approve"}), CONFIG)

    state = AgentState.model_validate((await graph.aget_state(CONFIG)).values)
    event = state.messages[-1].additional_kwargs["event"]
    assert event["code"] == "relationships_committed"
    assert event["params"]["created"] == "1"
    assert len(await SqliteEdgeStore(db_session).list_all(project.id)) == 1
