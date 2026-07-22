"""Composition root for the stdio MCP server, mirroring api/deps.py.

Separate from the FastAPI one on purpose: this process has no app lifespan to
hang resources off, and it must not import the web stack to get a database.
What the two share is the layer that matters — the services below own the
validation the REST API, the agent and these tools all have to agree on.

Settings resolve on first use rather than at import. A module that reads the
environment while being imported cannot be tested without one, which is how
this server ended up with no tests at all.
"""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from loregraph.config import Settings
from loregraph.llm.embeddings import get_embedding_provider
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
from loregraph.storage.vectorstore.chroma_store import ChromaVectorStore

_settings: Settings | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_vector_index: VectorIndex | None = None
_init_lock = asyncio.Lock()


async def get_session() -> AsyncSession:
    """A session against the local Loregraph database, initialising the
    engine and vector index on first call.

    The vector wiring matches the web app's: MCP writes have to be indexed
    too, or lore created here is invisible to the in-app agent's retrieval —
    which would defeat the point of sharing a service layer."""
    global _settings, _session_factory, _vector_index
    async with _init_lock:
        if _session_factory is None:
            _settings = _settings or Settings()
            engine = create_engine_for(_settings.db_path)
            await init_db(engine)
            _session_factory = make_session_factory(engine)
            embedder = get_embedding_provider(_settings)
            if embedder is not None:
                _vector_index = VectorIndex(
                    ChromaVectorStore(_settings.chroma_dir, embedder)
                )
    return _session_factory()


def entity_service(session: AsyncSession) -> EntityService:
    return EntityService(SqliteEntityStore(session), _vector_index)


def edge_service(session: AsyncSession) -> EdgeService:
    return EdgeService(SqliteEdgeStore(session), SqliteEntityStore(session))
