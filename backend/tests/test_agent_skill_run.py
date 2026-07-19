"""Phase 2 of the skills architecture (see agent/skills/registry.py): a
"propose"/"job" skill has two equally valid entry points — a chat tool call
(covered by test_agent_graph.py's propose_lore/edit_entity tests) and a
direct run via AgentRunner.stream_skill_run / POST .../skills/{name}/run,
with no assistant LLM call involved at all. These tests exercise the
second path and prove it reaches the identical pipeline deterministically."""

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
from loregraph.schemas.agent import DraftEntity, EntityEditDraft, LoreDraft
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


class ScriptedChatModel(BaseChatModel):
    """Never actually called by these tests (skill_kickoff bypasses the
    assistant node entirely) — an empty script proves that."""

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


def starter_lore() -> LoreDraft:
    return LoreDraft(
        entities=[
            DraftEntity(
                ref="e1", type="location", title="Норвинтер", summary="Портовый город."
            ),
        ],
        relationships=[],
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
async def test_skill_run_starts_propose_lore_without_any_llm_chat_call(
    db_session: AsyncSession,
) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    entity_store = SqliteEntityStore(db_session)
    edge_store = SqliteEdgeStore(db_session)
    graph = build_agent_graph(
        # Empty script: if route_entry ever fell through to "assistant" by
        # mistake, this would raise IndexError (deque.popleft on empty),
        # failing the test loudly instead of silently doing the wrong thing.
        chat_model=ScriptedChatModel(script=deque()),
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
    thread_id = "skill-run-thread"
    await sessions.create(project.id, thread_id)
    runner = AgentRunner(graph, sessions)

    events = [
        e
        async for e in runner.stream_skill_run(
            project.id, thread_id, "propose_lore", {"brief": "стартовый лор"}
        )
    ]

    review_events = [e for e in events if e["type"] == "review"]
    assert len(review_events) == 1
    assert review_events[0]["payload"]["draft"]["entities"][0]["title"] == "Норвинтер"

    detail = await runner.get_detail(project.id, thread_id)
    assert detail.status == "awaiting_review"


@pytest.mark.asyncio
async def test_skill_run_edit_entity_reaches_same_pipeline_as_chat(
    db_session: AsyncSession,
) -> None:
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
        chat_model=ScriptedChatModel(script=deque()),
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
    thread_id = "skill-run-edit-thread"
    await sessions.create(project.id, thread_id)
    runner = AgentRunner(graph, sessions)

    events = [
        e
        async for e in runner.stream_skill_run(
            project.id,
            thread_id,
            "edit_entity",
            {"entity_id": entity.id, "brief": "дай тёмное прошлое"},
        )
    ]

    review_events = [e for e in events if e["type"] == "review"]
    assert len(review_events) == 1
    assert review_events[0]["payload"]["entity_edit_draft"]["entity_id"] == entity.id


@pytest.mark.asyncio
async def test_skill_run_rejects_awaiting_review_session(
    db_session: AsyncSession,
) -> None:
    """Same conflict guard stream_message has — a skill run must not fire
    into a thread that already has a pending interrupt."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    entity_store = SqliteEntityStore(db_session)
    edge_store = SqliteEdgeStore(db_session)
    graph = build_agent_graph(
        chat_model=ScriptedChatModel(script=deque()),
        creative=FakeGenerator([starter_lore(), starter_lore()]),
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
    thread_id = "skill-run-conflict-thread"
    await sessions.create(project.id, thread_id)
    runner = AgentRunner(graph, sessions)

    await anext(
        e
        async for e in runner.stream_skill_run(
            project.id, thread_id, "propose_lore", {"brief": "первый"}
        )
        if e["type"] == "review"
    )

    events = [
        e
        async for e in runner.stream_skill_run(
            project.id, thread_id, "propose_lore", {"brief": "второй"}
        )
    ]
    assert events == [
        {
            "type": "error",
            "code": "awaiting_review_conflict",
            "detail": "A draft is awaiting review — approve, reject or "
            "request changes before running another skill.",
        }
    ]
