import hashlib
import logging
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.agent.nodes.retrieve_context import retrieve_context
from loregraph.agent.state import NO_KNOWLEDGE_SENTINEL, AgentState
from loregraph.schemas.project import ProjectCreate
from loregraph.services.knowledge_index import KnowledgeIndex
from loregraph.storage.sqlite.db import create_engine_for, init_db, make_session_factory
from loregraph.storage.sqlite.edge_store import SqliteEdgeStore
from loregraph.storage.sqlite.entity_store import SqliteEntityStore
from loregraph.storage.sqlite.project_store import SqliteProjectStore
from loregraph.storage.vectorstore.chroma_store import ChromaVectorStore


class FakeEmbedder:
    model_id = "fake-embedder-v1"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vectors.append([b / 255.0 for b in digest[:16]])
        return vectors


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
async def test_retrieve_context_populates_knowledge_context(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    store = ChromaVectorStore(tmp_path / "chroma", FakeEmbedder())
    knowledge_index = KnowledgeIndex(store)
    await knowledge_index.index_source(
        project.id, "src1", ["The setting is a gothic horror land called Barovia."]
    )

    state = AgentState(project_id=project.id, pending_brief="Tell me about the setting")
    update = await retrieve_context(
        state,
        vector_index=None,
        knowledge_index=knowledge_index,
        entity_store=SqliteEntityStore(db_session),
        edge_store=SqliteEdgeStore(db_session),
    )

    assert "Barovia" in update["knowledge_context"]
    assert "<kb_chunk" in update["knowledge_context"]
    # The knowledge base contour must stay separate from existing_lore's
    # grounded_in-eligible ids (see prompts/propose_changes.system.md rule 12).
    assert update["context_entity_ids"] == []


@pytest.mark.asyncio
async def test_retrieve_context_without_knowledge_index_uses_sentinel(
    db_session: AsyncSession,
) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    state = AgentState(project_id=project.id, pending_brief="Tell me about the setting")

    update = await retrieve_context(
        state,
        vector_index=None,
        knowledge_index=None,
        entity_store=SqliteEntityStore(db_session),
        edge_store=SqliteEdgeStore(db_session),
    )

    assert update["knowledge_context"] == NO_KNOWLEDGE_SENTINEL


# ---------------------------------------------------------------------------
# Diagnostics: "retrieval found nothing" must be distinguishable from
# "retrieval never ran because the knowledge base is unavailable" — both
# collapse to the same NO_KNOWLEDGE_SENTINEL in the prompt (by design, so the
# model never treats silence as evidence either way), so telling them apart
# needs a separate signal. Logs are that signal.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_context_logs_unavailable_when_no_knowledge_index(
    db_session: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    state = AgentState(project_id=project.id, pending_brief="Tell me about the setting")

    with caplog.at_level(
        logging.DEBUG, logger="loregraph.agent.nodes.retrieve_context"
    ):
        await retrieve_context(
            state,
            vector_index=None,
            knowledge_index=None,
            entity_store=SqliteEntityStore(db_session),
            edge_store=SqliteEdgeStore(db_session),
        )

    assert "kb_retrieval" in caplog.text
    assert "available=false" in caplog.text
    assert "attempted=false" in caplog.text
    assert project.id in caplog.text


@pytest.mark.asyncio
async def test_retrieve_context_logs_attempted_with_zero_hits(
    db_session: AsyncSession, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The knowledge base IS configured, but nothing was ever uploaded for
    this project (or nothing matched) — must read differently in the logs
    than "no embeddings configured at all", even though the prompt-facing
    NO_KNOWLEDGE_SENTINEL is identical in both cases."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    knowledge_index = KnowledgeIndex(
        ChromaVectorStore(tmp_path / "chroma", FakeEmbedder())
    )
    state = AgentState(project_id=project.id, pending_brief="Tell me about the setting")

    with caplog.at_level(
        logging.DEBUG, logger="loregraph.agent.nodes.retrieve_context"
    ):
        await retrieve_context(
            state,
            vector_index=None,
            knowledge_index=knowledge_index,
            entity_store=SqliteEntityStore(db_session),
            edge_store=SqliteEdgeStore(db_session),
        )

    assert "kb_retrieval" in caplog.text
    assert "available=true" in caplog.text
    assert "attempted=true" in caplog.text
    assert "hits=0" in caplog.text


@pytest.mark.asyncio
async def test_retrieve_context_logs_hit_count_on_a_match(
    db_session: AsyncSession, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    knowledge_index = KnowledgeIndex(
        ChromaVectorStore(tmp_path / "chroma", FakeEmbedder())
    )
    await knowledge_index.index_source(
        project.id, "src1", ["The setting is a gothic horror land called Barovia."]
    )
    state = AgentState(project_id=project.id, pending_brief="Tell me about the setting")

    with caplog.at_level(
        logging.DEBUG, logger="loregraph.agent.nodes.retrieve_context"
    ):
        await retrieve_context(
            state,
            vector_index=None,
            knowledge_index=knowledge_index,
            entity_store=SqliteEntityStore(db_session),
            edge_store=SqliteEdgeStore(db_session),
        )

    assert "available=true" in caplog.text
    assert "attempted=true" in caplog.text
    assert "hits=1" in caplog.text
    # Never the chunk text itself — campaign lore is often private.
    assert "Barovia" not in caplog.text
