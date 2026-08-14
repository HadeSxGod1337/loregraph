"""Editing an entity that already exists, through the unified propose_changes
pipeline: the assistant passes the entity's id in target_entity_ids, the
generator returns a patch (not a whole-row replace), and commit applies it
non-destructively.

The regression this whole file guards: a game master asking to "fill in Егор"
must EDIT Егор, never clone him, and the edit must never wipe fields, flags or
the template it did not touch.
"""

from collections import deque
from collections.abc import AsyncGenerator
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
from loregraph.agent.runner import AgentRunner
from loregraph.agent.state import AgentState
from loregraph.llm.structured import StructuredResult
from loregraph.llm.usage import LLMCallUsage
from loregraph.schemas.agent import (
    DraftEntityPatch,
    DraftField,
    GroundingReport,
    LoreDraft,
)
from loregraph.schemas.entity import EntityCreate, EntityFieldIn, FieldType
from loregraph.schemas.project import ProjectCreate
from loregraph.services.edge_service import EdgeService
from loregraph.services.entity_service import EntityService
from loregraph.services.vector_index import VectorIndex
from loregraph.storage.sqlite.agent_session_store import SqliteAgentSessionStore
from loregraph.storage.sqlite.db import (
    create_engine_for,
    init_db,
    make_session_factory,
)
from loregraph.storage.sqlite.edge_store import SqliteEdgeStore
from loregraph.storage.sqlite.entity_store import SqliteEntityStore
from loregraph.storage.sqlite.project_store import SqliteProjectStore
from tests.fakes import FixedVectorIndex


class ScriptedChatModel(BaseChatModel):
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
    def __init__(self, results: list[BaseModel]) -> None:
        self._results = deque(results)

    async def generate[T: BaseModel](
        self, schema: type[T], *, system: str, user: str, cached_prefix: str = ""
    ) -> StructuredResult[T]:
        value = self._results.popleft()
        assert isinstance(value, schema)
        return StructuredResult(value, LLMCallUsage(input_tokens=10, output_tokens=5))


@pytest_asyncio.fixture
async def db_session(tmp_path: Path) -> AsyncGenerator[AsyncSession, None]:
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


CONFIG: RunnableConfig = {"configurable": {"thread_id": "edit-t1"}}


def edit_call(entity_id: str, brief: str) -> AIMessage:
    """propose_changes with the entity named as a target — how an edit is
    expressed now (no separate edit_entity tool)."""
    return AIMessage(
        "",
        tool_calls=[
            {
                "name": "propose_changes",
                "args": {"brief": brief, "target_entity_ids": [entity_id]},
                "id": "ec1",
            }
        ],
    )


async def agent_state(graph: Any) -> AgentState:
    return AgentState.model_validate((await graph.aget_state(CONFIG)).values)


def _no_flags() -> list[BaseModel]:
    """The grounding judge runs whenever retrieval returned lore — hand it a
    clean report."""
    return [GroundingReport(claims_checked=0, claims_flagged=0, warnings=[])]


@pytest.mark.asyncio
async def test_edit_pipeline_interrupts_at_review(db_session: AsyncSession) -> None:
    """A propose_changes call that only patches an existing entity pauses at
    human_review with the patch in the draft."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    entity = await SqliteEntityStore(db_session).create(
        EntityCreate(type="npc", title="Мира Кузнец", fields=[]), project.id
    )
    draft = LoreDraft(
        patches=[
            DraftEntityPatch(
                entity_id=entity.id,
                set_fields=[
                    DraftField(key="backstory", value="Мастер-кузнец с тёмным прошлым.")
                ],
                edit_reason="Добавлено тёмное прошлое.",
            )
        ]
    )
    graph = make_graph(
        db_session,
        [edit_call(entity.id, "дай Мире тёмное прошлое")],
        creative_results=[draft],
        extraction_results=_no_flags(),
        retrieved_entity_ids=[entity.id],
    )
    await graph.ainvoke(
        {"project_id": project.id, "messages": [HumanMessage("отредактируй Миру")]},
        CONFIG,
    )

    snapshot = await graph.aget_state(CONFIG)
    assert any(task.interrupts for task in snapshot.tasks), "review gate must interrupt"

    state = await agent_state(graph)
    assert state.draft is not None
    assert len(state.draft.patches) == 1
    assert state.draft.patches[0].entity_id == entity.id
    assert "тёмным" in state.draft.patches[0].set_fields[0].value


@pytest.mark.asyncio
async def test_edit_approve_patches_entity(db_session: AsyncSession) -> None:
    """Approving applies the patch through entity_service.patch."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    entity_store = SqliteEntityStore(db_session)
    entity = await entity_store.create(
        EntityCreate(type="npc", title="Мира Кузнец", fields=[]), project.id
    )
    draft = LoreDraft(
        patches=[
            DraftEntityPatch(
                entity_id=entity.id,
                title="Мира Молот",  # rename
                edit_reason="Имя изменено по просьбе ДМа.",
            )
        ]
    )
    graph = make_graph(
        db_session,
        [edit_call(entity.id, "переименуй Миру в Молот")],
        creative_results=[draft],
        extraction_results=_no_flags(),
        retrieved_entity_ids=[entity.id],
    )
    await graph.ainvoke(
        {"project_id": project.id, "messages": [HumanMessage("переименуй")]},
        CONFIG,
    )
    await graph.ainvoke(Command(resume={"action": "approve"}), CONFIG)

    state = await agent_state(graph)
    assert state.draft_committed
    assert entity.id in state.committed_entity_ids
    updated = await entity_store.get(entity.id)
    assert updated.title == "Мира Молот"
    assert state.messages[-1].additional_kwargs.get("event", {}).get("code") == (
        "changes_committed"
    )


@pytest.mark.asyncio
async def test_edit_is_non_destructive(db_session: AsyncSession) -> None:
    """The core guarantee: patching one field leaves every other field, its
    flags, and the template intact — the data-loss bug the pipeline had when
    an edit was a whole-row EntityUpdate built from flat text the model saw."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    entity_store = SqliteEntityStore(db_session)
    entity = await entity_store.create(
        EntityCreate(
            type="npc",
            title="Егор",
            template_id="tmpl_hero",
            fields=[
                EntityFieldIn(
                    key="secret",
                    field_type=FieldType.TEXT,
                    value="прячет артефакт",
                    visible_to_players=False,
                ),
                EntityFieldIn(
                    key="motto",
                    field_type=FieldType.TEXT,
                    value="вперёд",
                    show_on_card=True,
                ),
            ],
        ),
        project.id,
    )
    draft = LoreDraft(
        patches=[
            DraftEntityPatch(
                entity_id=entity.id,
                set_fields=[DraftField(key="role", value="маг-артефактор")],
                edit_reason="Заполнена роль.",
            )
        ]
    )
    graph = make_graph(
        db_session,
        [edit_call(entity.id, "придумай кто такой Егор и добавь поля")],
        creative_results=[draft],
        extraction_results=_no_flags(),
        retrieved_entity_ids=[entity.id],
    )
    await graph.ainvoke(
        {"project_id": project.id, "messages": [HumanMessage("заполни Егора")]},
        CONFIG,
    )
    await graph.ainvoke(Command(resume={"action": "approve"}), CONFIG)

    updated = await entity_store.get(entity.id)
    by_key = {f.key: f for f in updated.fields}
    # New field added.
    assert by_key["role"].value == "маг-артефактор"
    # Untouched fields survive with their flags.
    assert by_key["secret"].value == "прячет артефакт"
    assert by_key["secret"].visible_to_players is False
    assert by_key["motto"].show_on_card is True
    # Template survives — nothing in the draft named it.
    assert updated.template_id == "tmpl_hero"


@pytest.mark.asyncio
async def test_edit_reject_leaves_entity_unchanged(db_session: AsyncSession) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    entity_store = SqliteEntityStore(db_session)
    entity = await entity_store.create(
        EntityCreate(type="npc", title="Мира Кузнец", fields=[]), project.id
    )
    draft = LoreDraft(
        patches=[
            DraftEntityPatch(
                entity_id=entity.id, title="Мира Молот", edit_reason="Тест."
            )
        ]
    )
    graph = make_graph(
        db_session,
        [edit_call(entity.id, "переименуй")],
        creative_results=[draft],
        extraction_results=_no_flags(),
        retrieved_entity_ids=[entity.id],
    )
    await graph.ainvoke(
        {"project_id": project.id, "messages": [HumanMessage("переименуй")]},
        CONFIG,
    )
    await graph.ainvoke(Command(resume={"action": "reject"}), CONFIG)

    state = await agent_state(graph)
    assert state.committed_entity_ids == []
    unchanged = await entity_store.get(entity.id)
    assert unchanged.title == "Мира Кузнец"


@pytest.mark.asyncio
async def test_patch_to_unknown_entity_is_dropped_with_warning(
    db_session: AsyncSession,
) -> None:
    """A patch whose target does not exist must not reach commit — it is
    dropped with a warning at validation, never silently writing nothing."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    draft = LoreDraft(
        patches=[
            DraftEntityPatch(
                entity_id="ghost-id",
                set_fields=[DraftField(key="x", value="y")],
                edit_reason="—",
            )
        ]
    )
    graph = make_graph(
        db_session,
        [edit_call("ghost-id", "правь призрака")],
        creative_results=[draft],
    )
    await graph.ainvoke(
        {"project_id": project.id, "messages": [HumanMessage("правь")]},
        CONFIG,
    )
    state = await agent_state(graph)
    assert state.draft is not None
    assert state.draft.patches == []
    assert any(w.code == "patch_unknown_entity" for w in state.warnings)


@pytest.mark.asyncio
async def test_edit_review_survives_session_registry_round_trip(
    db_session: AsyncSession,
) -> None:
    """The frontend reads the review through AgentReviewPayload persisted as
    JSON, not AgentState directly. A patch-carrying draft must survive that
    round trip so the review card can render the edit."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    entity_store = SqliteEntityStore(db_session)
    edge_store = SqliteEdgeStore(db_session)
    entity = await entity_store.create(
        EntityCreate(type="npc", title="Мира Кузнец", fields=[]), project.id
    )
    draft = LoreDraft(
        patches=[
            DraftEntityPatch(
                entity_id=entity.id,
                set_fields=[
                    DraftField(key="backstory", value="Мастер-кузнец с тёмным прошлым.")
                ],
                edit_reason="Добавлено тёмное прошлое.",
            )
        ]
    )
    graph = build_agent_graph(
        chat_model=ScriptedChatModel(
            script=deque([edit_call(entity.id, "дай Мире тёмное прошлое")])
        ),
        creative=FakeGenerator([draft]),
        extraction=FakeGenerator(
            [GroundingReport(claims_checked=0, claims_flagged=0, warnings=[])]
        ),
        vector_index=cast(VectorIndex, FixedVectorIndex([entity.id])),
        knowledge_index=None,
        entity_store=entity_store,
        edge_store=edge_store,
        project_store=SqliteProjectStore(db_session),
        entity_service=EntityService(entity_store),
        edge_service=EdgeService(edge_store, entity_store),
        token_budget=100_000,
        checkpointer=MemorySaver(),
    )
    sessions = SqliteAgentSessionStore(db_session)
    thread_id = "edit-round-trip"
    await sessions.create(project.id, thread_id)
    runner = AgentRunner(graph, sessions)

    events = [
        event
        async for event in runner.stream_message(
            project.id, thread_id, "отредактируй Миру", None, []
        )
    ]
    review_events = [e for e in events if e["type"] == "review"]
    assert len(review_events) == 1
    patches = review_events[0]["payload"]["draft"]["patches"]
    assert patches[0]["entity_id"] == entity.id

    detail = await runner.get_detail(project.id, thread_id)
    assert detail.status == "awaiting_review"
    assert detail.review is not None
    assert detail.review.draft is not None
    assert detail.review.draft.patches[0].entity_id == entity.id
    assert "тёмным" in detail.review.draft.patches[0].set_fields[0].value
