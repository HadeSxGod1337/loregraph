import hashlib
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.schemas.project import ProjectCreate
from loregraph.services.knowledge_index import KnowledgeIndex
from loregraph.services.knowledge_ingest import ingest_source
from loregraph.storage.sqlite.db import create_engine_for, init_db, make_session_factory
from loregraph.storage.sqlite.knowledge_source_store import SqliteKnowledgeSourceStore
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
async def test_ingest_source_happy_path_marks_ready(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    store = SqliteKnowledgeSourceStore(db_session, tmp_path / "knowledge")
    source = await store.create(
        project_id=project.id,
        original_filename="notes.txt",
        content_type="text/plain",
        content=b"Some setting notes.\n\nMore lore here.",
    )
    index = KnowledgeIndex(ChromaVectorStore(tmp_path / "chroma", FakeEmbedder()))

    await ingest_source(
        source.id,
        project.id,
        b"Some setting notes.\n\nMore lore here.",
        "text/plain",
        "notes.txt",
        source_store=store,
        knowledge_index=index,
    )

    updated = await store.get(source.id)
    assert updated.status == "ready"
    # Both paragraphs are short enough to pack into a single chunk (default
    # KB_CHUNK_MAX_CHARS=1500) — see test_document_ingest.py for chunk_text's
    # packing/splitting behavior in isolation.
    assert updated.chunk_count == 1
    hits = await index.query(project.id, "setting notes", k=5)
    assert hits


@pytest.mark.asyncio
async def test_ingest_source_unsupported_type_marks_failed(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    store = SqliteKnowledgeSourceStore(db_session, tmp_path / "knowledge")
    source = await store.create(
        project_id=project.id,
        original_filename="art.png",
        content_type="image/png",
        content=b"not-a-real-image",
    )
    index = KnowledgeIndex(ChromaVectorStore(tmp_path / "chroma", FakeEmbedder()))

    await ingest_source(
        source.id,
        project.id,
        b"not-a-real-image",
        "image/png",
        "art.png",
        source_store=store,
        knowledge_index=index,
    )

    updated = await store.get(source.id)
    assert updated.status == "failed"
    assert updated.error is not None


@pytest.mark.asyncio
async def test_ingest_source_without_knowledge_index_degrades_to_ready(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """Embeddings disabled (knowledge_index=None): the file is stored and
    listable, just not searchable — same degrade contract as VectorIndex."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    store = SqliteKnowledgeSourceStore(db_session, tmp_path / "knowledge")
    source = await store.create(
        project_id=project.id,
        original_filename="notes.txt",
        content_type="text/plain",
        content=b"Text.",
    )

    await ingest_source(
        source.id,
        project.id,
        b"Text.",
        "text/plain",
        "notes.txt",
        source_store=store,
        knowledge_index=None,
    )

    updated = await store.get(source.id)
    assert updated.status == "ready"
    assert updated.chunk_count == 0
    assert updated.error is None


@pytest.mark.asyncio
async def test_knowledge_source_store_crud(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    store = SqliteKnowledgeSourceStore(db_session, tmp_path / "knowledge")

    created = await store.create(
        project_id=project.id,
        original_filename="rules.pdf",
        content_type="application/pdf",
        content=b"pdf-bytes",
    )
    assert created.status == "pending"
    assert created.chunk_count == 0

    listed = await store.list_for_project(project.id)
    assert [s.id for s in listed] == [created.id]

    updated = await store.update_status(created.id, status="ready", chunk_count=3)
    assert updated.status == "ready"
    assert updated.chunk_count == 3

    dest = tmp_path / "knowledge" / project.id
    assert any(dest.iterdir())

    await store.delete(created.id)
    assert await store.list_for_project(project.id) == []
    assert not any(dest.iterdir())
