import hashlib
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.agent.nodes.retrieve_context import (
    NO_KNOWLEDGE_SENTINEL,
    retrieve_context,
)
from loregraph.agent.state import AgentState
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
    # grounded_in-eligible ids (see prompts/generate_lore.system.md rule 12).
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
