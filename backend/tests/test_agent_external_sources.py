"""The agent side of live external sources: the chat tool dispatch and the
grounding fan-out, both against fake LiveSources — the invariant under test
is graceful degradation (an offline Foundry never breaks a turn)."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from langchain_core.messages import AIMessage
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.agent.nodes.assistant import external_sources_block
from loregraph.agent.nodes.retrieve_context import retrieve_context
from loregraph.agent.nodes.tools import run_tools
from loregraph.agent.state import AgentState
from loregraph.connectors.live import LiveSourceEntry, LiveSourceProvider
from loregraph.connectors.protocols import ExternalChunk
from loregraph.exceptions import ConnectorUnavailableError
from loregraph.prompts import render
from loregraph.schemas.project import ProjectCreate
from loregraph.storage.sqlite.db import (
    create_engine_for,
    init_db,
    make_session_factory,
)
from loregraph.storage.sqlite.edge_store import SqliteEdgeStore
from loregraph.storage.sqlite.entity_store import SqliteEntityStore
from loregraph.storage.sqlite.project_store import SqliteProjectStore


class FakeLiveSource:
    def __init__(self, chunks: list[ExternalChunk] | None = None) -> None:
        self.chunks = chunks or []
        self.queries: list[str] = []

    async def query(self, query: str, kind: str | None = None) -> list[ExternalChunk]:
        self.queries.append(query)
        return self.chunks


class OfflineLiveSource:
    async def query(self, query: str, kind: str | None = None) -> list[ExternalChunk]:
        raise ConnectorUnavailableError("My Foundry", "connection refused")


def _chunk(text: str) -> ExternalChunk:
    return ExternalChunk(
        source_name="My Foundry",
        connector_type="foundry",
        kind="journal",
        title="Session 3",
        text=text,
    )


def _provider(source: object, *, grounding: bool = True) -> LiveSourceProvider:
    return LiveSourceProvider(
        [
            LiveSourceEntry(
                name="My Foundry",
                connector_type="foundry",
                use_for_grounding=grounding,
                source=source,  # type: ignore[arg-type]
            )
        ]
    )


def _tool_call_state(source: str) -> AgentState:
    call = {
        "name": "query_external_source",
        "args": {"source": source, "query": "vampire"},
        "id": "call-1",
    }
    return AgentState(project_id="p1", messages=[AIMessage("", tool_calls=[call])])


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
async def test_query_external_source_returns_chunks(
    db_session: AsyncSession,
) -> None:
    provider = _provider(FakeLiveSource([_chunk("The party met Strahd.")]))
    update = await run_tools(
        _tool_call_state("My Foundry"),
        vector_index=None,
        knowledge_index=None,
        entity_store=SqliteEntityStore(db_session),
        live_sources=provider,
    )
    content = update["messages"][0].content
    assert "Session 3" in content and "Strahd" in content


@pytest.mark.asyncio
async def test_query_external_source_unknown_name_lists_available(
    db_session: AsyncSession,
) -> None:
    provider = _provider(FakeLiveSource())
    update = await run_tools(
        _tool_call_state("Nonexistent"),
        vector_index=None,
        knowledge_index=None,
        entity_store=SqliteEntityStore(db_session),
        live_sources=provider,
    )
    content = update["messages"][0].content
    assert "Unknown external source" in content
    assert "My Foundry" in content


@pytest.mark.asyncio
async def test_query_external_source_offline_yields_message_not_exception(
    db_session: AsyncSession,
) -> None:
    provider = _provider(OfflineLiveSource())
    update = await run_tools(
        _tool_call_state("My Foundry"),
        vector_index=None,
        knowledge_index=None,
        entity_store=SqliteEntityStore(db_session),
        live_sources=provider,
    )
    content = update["messages"][0].content
    assert "unavailable" in content


@pytest.mark.asyncio
async def test_query_external_source_returns_all_chunks_within_connector_budget(
    db_session: AsyncSession,
) -> None:
    """Regression: a connector's own per-kind budget (e.g. Foundry's world
    items, up to 30) must reach the chat reply intact — this generic tool-
    level cap (EXTERNAL_CHUNK_LIMIT) must not silently re-truncate it back
    down to a much smaller number with no indication anything was cut."""
    many_chunks = [_chunk(f"Item {i}") for i in range(20)]
    provider = _provider(FakeLiveSource(many_chunks))
    update = await run_tools(
        _tool_call_state("My Foundry"),
        vector_index=None,
        knowledge_index=None,
        entity_store=SqliteEntityStore(db_session),
        live_sources=provider,
    )
    content = update["messages"][0].content
    for i in range(20):
        assert f"Item {i}" in content
    assert "showing" not in content  # nothing was cut, no truncation note


@pytest.mark.asyncio
async def test_query_external_source_notes_truncation_when_it_does_happen(
    db_session: AsyncSession,
) -> None:
    """When a connector legitimately returns more than the safety-net cap,
    the reply must say so explicitly rather than silently presenting a
    partial list as complete."""
    too_many_chunks = [_chunk(f"Item {i}") for i in range(80)]
    provider = _provider(FakeLiveSource(too_many_chunks))
    update = await run_tools(
        _tool_call_state("My Foundry"),
        vector_index=None,
        knowledge_index=None,
        entity_store=SqliteEntityStore(db_session),
        live_sources=provider,
    )
    content = update["messages"][0].content
    assert "showing 65 of 80 results" in content


@pytest.mark.asyncio
async def test_grounding_includes_external_source_chunks(
    db_session: AsyncSession,
) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    provider = _provider(FakeLiveSource([_chunk("Party is level 5, HP low.")]))
    state = AgentState(project_id=project.id, pending_brief="a new encounter")
    update = await retrieve_context(
        state,
        vector_index=None,
        knowledge_index=None,
        entity_store=SqliteEntityStore(db_session),
        edge_store=SqliteEdgeStore(db_session),
        live_sources=provider,
    )
    assert '<external_source name="My Foundry"' in update["knowledge_context"]
    assert "Party is level 5" in update["knowledge_context"]
    # External data never becomes a grounded_in-eligible entity id.
    assert update["context_entity_ids"] == []


@pytest.mark.asyncio
async def test_grounding_survives_offline_source(
    db_session: AsyncSession,
) -> None:
    """The plan's hard invariant: kill Foundry — generation still proceeds."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    provider = _provider(OfflineLiveSource())
    state = AgentState(project_id=project.id, pending_brief="a new encounter")
    update = await retrieve_context(
        state,
        vector_index=None,
        knowledge_index=None,
        entity_store=SqliteEntityStore(db_session),
        edge_store=SqliteEdgeStore(db_session),
        live_sources=provider,
    )
    assert "<external_source" not in update["knowledge_context"]
    assert "existing_lore" in update  # the node completed normally


@pytest.mark.asyncio
async def test_grounding_skips_sources_not_marked_for_grounding(
    db_session: AsyncSession,
) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    source = FakeLiveSource([_chunk("should not appear")])
    provider = _provider(source, grounding=False)
    state = AgentState(project_id=project.id, pending_brief="anything")
    update = await retrieve_context(
        state,
        vector_index=None,
        knowledge_index=None,
        entity_store=SqliteEntityStore(db_session),
        edge_store=SqliteEdgeStore(db_session),
        live_sources=provider,
    )
    assert source.queries == []
    assert "<external_source" not in update["knowledge_context"]


def test_assistant_prompt_lists_external_sources() -> None:
    provider = _provider(FakeLiveSource())
    rendered = render(
        "assistant.system.md",
        project_instructions_block="",
        external_sources_block=external_sources_block(provider),
        mcp_tools_block="",
    )
    assert "<external_sources" in rendered
    assert "My Foundry (foundry)" in rendered


def test_assistant_prompt_omits_block_without_sources() -> None:
    rendered = render(
        "assistant.system.md",
        project_instructions_block="",
        external_sources_block=external_sources_block(None),
        mcp_tools_block="",
    )
    # The block with the note attribute should be absent when there are no
    # sources — rule 7 in the prose may still reference the concept by name.
    assert "<external_sources note=" not in rendered
