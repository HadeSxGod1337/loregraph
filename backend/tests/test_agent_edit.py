from collections import deque
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

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
from loregraph.schemas.agent import EntityEditDraft
from loregraph.schemas.entity import EntityCreate
from loregraph.schemas.project import ProjectCreate
from loregraph.services.edge_service import EdgeService
from loregraph.services.entity_service import EntityService
from loregraph.storage.sqlite.agent_session_store import SqliteAgentSessionStore
from loregraph.storage.sqlite.db import (
    create_engine_for,
    init_db,
    make_session_factory,
)
from loregraph.storage.sqlite.edge_store import SqliteEdgeStore
from loregraph.storage.sqlite.entity_store import SqliteEntityStore
from loregraph.storage.sqlite.project_store import SqliteProjectStore

# ---------------------------------------------------------------------------
# Helpers reused from test_agent_graph.py
# ---------------------------------------------------------------------------


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
) -> Any:
    entity_store = SqliteEntityStore(session)
    edge_store = SqliteEdgeStore(session)
    return build_agent_graph(
        chat_model=ScriptedChatModel(script=deque(script)),
        creative=FakeGenerator(creative_results or []),
        extraction=FakeGenerator([]),
        vector_index=None,
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
    return AIMessage(
        "",
        tool_calls=[
            {
                "name": "edit_entity",
                "args": {"entity_id": entity_id, "brief": brief},
                "id": "ec1",
            }
        ],
    )


def state_values(graph: Any) -> dict[str, Any]:
    import asyncio

    result: dict[str, Any] = asyncio.get_event_loop().run_until_complete(
        graph.aget_state(CONFIG)
    ).values
    return result


async def agent_state(graph: Any) -> AgentState:
    return AgentState.model_validate((await graph.aget_state(CONFIG)).values)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_pipeline_interrupts_at_review(db_session: AsyncSession) -> None:
    """edit_entity call → graph pauses at human_review with entity_edit_draft."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    entity = await SqliteEntityStore(db_session).create(
        EntityCreate(type="npc", title="Мира Кузнец", fields=[]), project.id
    )

    edit_draft = EntityEditDraft(
        entity_id=entity.id,
        type="npc",
        title="Мира Кузнец",
        summary="Мастер-кузнец с тёмным прошлым.",
        edit_reason="Добавлено тёмное прошлое.",
    )

    graph = make_graph(
        db_session,
        [edit_call(entity.id, "дай Мире тёмное прошлое")],
        creative_results=[edit_draft],
    )
    await graph.ainvoke(
        {"project_id": project.id, "messages": [HumanMessage("отредактируй Миру")]},
        CONFIG,
    )

    snapshot = await graph.aget_state(CONFIG)
    assert any(task.interrupts for task in snapshot.tasks), "review gate must interrupt"

    state = await agent_state(graph)
    assert state.entity_edit_draft is not None
    assert state.entity_edit_draft.entity_id == entity.id
    assert "тёмным" in state.entity_edit_draft.summary


@pytest.mark.asyncio
async def test_edit_approve_updates_entity(db_session: AsyncSession) -> None:
    """Approving an edit draft calls entity_service.update and the entity is
    updated in the DB."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    entity_store = SqliteEntityStore(db_session)
    entity = await entity_store.create(
        EntityCreate(type="npc", title="Мира Кузнец", fields=[]), project.id
    )

    edit_draft = EntityEditDraft(
        entity_id=entity.id,
        type="npc",
        title="Мира Молот",          # title changed
        summary="Переименована в Молот.",
        edit_reason="Имя изменено по просьбе ДМа.",
    )

    graph = make_graph(
        db_session,
        [edit_call(entity.id, "переименуй Миру в Молот")],
        creative_results=[edit_draft],
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

    # Event message must be in the transcript
    last_msg = state.messages[-1]
    assert last_msg.additional_kwargs.get("event", {}).get("code") == "entity_updated"


@pytest.mark.asyncio
async def test_edit_reject_leaves_entity_unchanged(db_session: AsyncSession) -> None:
    """Rejecting an edit draft must not touch the entity."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    entity_store = SqliteEntityStore(db_session)
    original_title = "Мира Кузнец"
    entity = await entity_store.create(
        EntityCreate(type="npc", title=original_title, fields=[]), project.id
    )

    edit_draft = EntityEditDraft(
        entity_id=entity.id,
        type="npc",
        title="Мира Молот",
        summary="Переименована.",
        edit_reason="Тест.",
    )

    graph = make_graph(
        db_session,
        [edit_call(entity.id, "переименуй")],
        creative_results=[edit_draft],
    )
    await graph.ainvoke(
        {"project_id": project.id, "messages": [HumanMessage("переименуй")]},
        CONFIG,
    )
    await graph.ainvoke(Command(resume={"action": "reject"}), CONFIG)

    state = await agent_state(graph)
    assert state.committed_entity_ids == []
    assert state.entity_edit_draft is None

    unchanged = await entity_store.get(entity.id)
    assert unchanged.title == original_title


@pytest.mark.asyncio
async def test_edit_nonexistent_entity_fails_gracefully(
    db_session: AsyncSession,
) -> None:
    """If the target entity doesn't exist, generate_edit emits edit_failed
    and the session does not crash."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))

    graph = make_graph(
        db_session,
        [edit_call("nonexistent-id", "change something")],
        creative_results=[],  # generate_edit should not reach LLM call
    )
    await graph.ainvoke(
        {"project_id": project.id, "messages": [HumanMessage("edit")]},
        CONFIG,
    )

    state = await agent_state(graph)
    # No review interrupt — failed before that point
    snapshot = await graph.aget_state(CONFIG)
    assert not any(task.interrupts for task in snapshot.tasks)
    assert state.entity_edit_draft is None


@pytest.mark.asyncio
async def test_edit_review_survives_session_registry_round_trip(
    db_session: AsyncSession,
) -> None:
    """The frontend never reads AgentState directly: the live SSE 'review'
    event and a reopened session (SessionPicker -> openSession -> GET
    .../sessions/{id}) both go through AgentReviewPayload persisted as JSON
    on the AgentSessionRow. Regression guard for entity_edit_draft getting
    dropped anywhere in that path — the graph-level tests above only prove
    it exists in AgentState, not that it survives the registry round trip."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    entity_store = SqliteEntityStore(db_session)
    edge_store = SqliteEdgeStore(db_session)
    entity = await entity_store.create(
        EntityCreate(type="npc", title="Мира Кузнец", fields=[]), project.id
    )
    edit_draft = EntityEditDraft(
        entity_id=entity.id,
        type="npc",
        title="Мира Кузнец",
        summary="Мастер-кузнец с тёмным прошлым.",
        edit_reason="Добавлено тёмное прошлое.",
    )
    graph = build_agent_graph(
        chat_model=ScriptedChatModel(
            script=deque([edit_call(entity.id, "дай Мире тёмное прошлое")])
        ),
        creative=FakeGenerator([edit_draft]),
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
    assert review_events[0]["payload"]["entity_edit_draft"]["entity_id"] == entity.id

    # Reopen it exactly as SessionPicker.openSession() does — a fresh read
    # from the registry, not the same in-memory AgentState.
    detail = await runner.get_detail(project.id, thread_id)
    assert detail.status == "awaiting_review"
    assert detail.review is not None
    assert detail.review.entity_edit_draft is not None
    assert detail.review.entity_edit_draft.entity_id == entity.id
    assert "тёмным" in detail.review.entity_edit_draft.summary
    # The batch-create field must stay unset — the two review shapes are
    # mutually exclusive, and the frontend's routing (draft vs
    # entity_edit_draft) depends on that.
    assert detail.review.draft is None
