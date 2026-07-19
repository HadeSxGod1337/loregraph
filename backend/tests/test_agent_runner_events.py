"""AgentRunner also publishes onto the EventBus alongside its SSE events
(see agent/runner.py::AgentRunner._stream_turn) — this is the WebSocket-
facing notification channel described in CLAUDE.md's event-driven core.
The SSE contract itself is already covered by test_agent_edit.py /
test_agent_graph.py; these tests only assert the bus mirrors it."""

from collections import deque
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.agent.graph import build_agent_graph
from loregraph.agent.runner import AgentRunner
from loregraph.llm.structured import StructuredResult
from loregraph.llm.usage import LLMCallUsage
from loregraph.schemas.agent import (
    AgentResumeRequest,
    DraftEntity,
    DraftRelationship,
    LoreDraft,
)
from loregraph.schemas.project import ProjectCreate
from loregraph.services.edge_service import EdgeService
from loregraph.services.entity_service import EntityService
from loregraph.services.event_bus import (
    EVENT_CHAT_DONE,
    EVENT_CHAT_STATUS,
    EVENT_REVIEW_REQUESTED,
    EVENT_WORLD_ENTITY_COMMITTED,
    EventBus,
)
from loregraph.storage.sqlite.agent_session_store import SqliteAgentSessionStore
from loregraph.storage.sqlite.db import (
    create_engine_for,
    init_db,
    make_session_factory,
)
from loregraph.storage.sqlite.edge_store import SqliteEdgeStore
from loregraph.storage.sqlite.entity_store import SqliteEntityStore
from loregraph.storage.sqlite.project_store import SqliteProjectStore


class ScriptedChatModel(BaseChatModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    script: deque[AIMessage]

    def bind_tools(self, tools: Any, **kwargs: Any) -> Runnable[Any, Any]:
        return self

    def _generate(
        self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self.script.popleft())])

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
        return StructuredResult(value, LLMCallUsage(input_tokens=100, output_tokens=50))


def propose_call(brief: str) -> AIMessage:
    return AIMessage(
        "", tool_calls=[{"name": "propose_lore", "args": {"brief": brief}, "id": "tc1"}]
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


@pytest.mark.asyncio
async def test_propose_then_approve_mirrors_sse_events_onto_the_bus(
    db_session: AsyncSession,
) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    entity_store = SqliteEntityStore(db_session)
    edge_store = SqliteEdgeStore(db_session)
    graph = build_agent_graph(
        chat_model=ScriptedChatModel(
            script=deque([propose_call("стартовый лор северного города")])
        ),
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
    )
    sessions = SqliteAgentSessionStore(db_session)
    thread_id = "events-thread"
    await sessions.create(project.id, thread_id)
    event_bus = EventBus()
    runner = AgentRunner(graph, sessions, event_bus=event_bus)

    sse_events = [
        e
        async for e in runner.stream_message(
            project.id, thread_id, "Создай стартовый лор", None, []
        )
    ]
    assert any(e["type"] == "review" for e in sse_events)

    channel = event_bus._channel(project.id)
    bus_types = [e.type for e in channel._buffer]
    assert EVENT_CHAT_STATUS in bus_types
    assert EVENT_REVIEW_REQUESTED in bus_types
    review_events = [e for e in channel._buffer if e.type == EVENT_REVIEW_REQUESTED]
    assert review_events[0].payload["thread_id"] == thread_id
    assert review_events[0].payload["payload"]["draft"] is not None

    sse_events = [
        e
        async for e in runner.stream_review(
            project.id, thread_id, AgentResumeRequest(action="approve")
        )
    ]
    assert any(e["type"] == "done" for e in sse_events)

    bus_types_after = [e.type for e in channel._buffer]
    assert bus_types_after.count(EVENT_WORLD_ENTITY_COMMITTED) == 2  # 2 entities
    assert EVENT_CHAT_DONE in bus_types_after


@pytest.mark.asyncio
async def test_runner_without_event_bus_behaves_exactly_as_before(
    db_session: AsyncSession,
) -> None:
    """Additive dependency: omitting event_bus must not change any SSE
    behavior — this is the existing test_agent_edit.py contract, repeated
    here as a guard against a regression introduced by this change."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    entity_store = SqliteEntityStore(db_session)
    edge_store = SqliteEdgeStore(db_session)
    graph = build_agent_graph(
        chat_model=ScriptedChatModel(
            script=deque([AIMessage("Ответ без предложений.")])
        ),
        creative=FakeGenerator([]),
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
    thread_id = "no-bus-thread"
    await sessions.create(project.id, thread_id)
    runner = AgentRunner(graph, sessions)  # no event_bus passed

    events = [
        e
        async for e in runner.stream_message(project.id, thread_id, "Привет", None, [])
    ]
    assert any(e["type"] == "done" for e in events)
