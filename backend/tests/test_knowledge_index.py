import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from loregraph.schemas.entity import EntityFieldOut, EntityOut, FieldType
from loregraph.services.knowledge_index import KnowledgeIndex
from loregraph.services.vector_index import VectorIndex, entity_to_text
from loregraph.storage.vectorstore.chroma_store import ChromaVectorStore


class FakeEmbedder:
    """Deterministic embeddings without any model download — same rationale
    as test_vector_index.py's FakeEmbedder."""

    model_id = "fake-embedder-v1"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vectors.append([b / 255.0 for b in digest[:16]])
        return vectors


@pytest.mark.asyncio
async def test_index_query_and_remove(tmp_path: Path) -> None:
    index = KnowledgeIndex(ChromaVectorStore(tmp_path / "chroma", FakeEmbedder()))
    await index.index_source("proj1", "src1", ["Chunk about the Barovian mist."])

    results = await index.query("proj1", "Chunk about the Barovian mist.", k=1)
    assert results and results[0].entity_id == "src1:0"

    await index.remove_source("proj1", "src1", chunk_count=1)
    assert await index.query("proj1", "Barovian mist", k=1) == []


@pytest.mark.asyncio
async def test_multiple_chunks_get_distinct_ids(tmp_path: Path) -> None:
    index = KnowledgeIndex(ChromaVectorStore(tmp_path / "chroma", FakeEmbedder()))
    await index.index_source("proj1", "src1", ["First chunk.", "Second chunk."])

    hits = await index.query("proj1", "chunk", k=5)
    assert {chunk.entity_id for chunk in hits} == {"src1:0", "src1:1"}


@pytest.mark.asyncio
async def test_namespace_is_isolated_from_the_entity_canon_collection(
    tmp_path: Path,
) -> None:
    """The knowledge base must never leak into (or read from) VectorIndex's
    p_{project_id} collection — same ChromaVectorStore, different namespace."""
    store = ChromaVectorStore(tmp_path / "chroma", FakeEmbedder())
    vector_index = VectorIndex(store)
    knowledge_index = KnowledgeIndex(store)

    entity = EntityOut(
        id="e1",
        project_id="proj1",
        type="npc",
        title="Мира Кузнец",
        fields=[EntityFieldOut(key="role", field_type=FieldType.TEXT, value="smith")],
        icon=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    await vector_index.index_entity(entity)
    await knowledge_index.index_source("proj1", "src1", ["Unrelated rulebook text."])

    canon_hits = await vector_index.query("proj1", entity_to_text(entity), k=5)
    assert {hit.entity_id for hit in canon_hits} == {"e1"}
    kb_hits = await knowledge_index.query("proj1", "Unrelated rulebook text.", k=5)
    assert {hit.entity_id for hit in kb_hits} == {"src1:0"}


@pytest.mark.asyncio
async def test_project_isolation(tmp_path: Path) -> None:
    index = KnowledgeIndex(ChromaVectorStore(tmp_path / "chroma", FakeEmbedder()))
    await index.index_source("proj1", "src1", ["Only in project one."])
    assert await index.query("proj2", "Only in project one.", k=5) == []


@pytest.mark.asyncio
async def test_drop_project(tmp_path: Path) -> None:
    index = KnowledgeIndex(ChromaVectorStore(tmp_path / "chroma", FakeEmbedder()))
    await index.index_source("proj1", "src1", ["Some reference text."])
    await index.drop_project("proj1")
    assert await index.query("proj1", "Some reference text.", k=5) == []
