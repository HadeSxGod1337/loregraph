import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from loregraph.schemas.entity import EntityFieldOut, EntityOut, FieldType
from loregraph.services.vector_index import VectorIndex, entity_to_text
from loregraph.storage.vectorstore.chroma_store import ChromaVectorStore


class FakeEmbedder:
    """Deterministic embeddings without any model download: hash-based, so
    identical texts map to identical vectors and the store's ranking is
    stable in tests."""

    model_id = "fake-embedder-v1"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vectors.append([b / 255.0 for b in digest[:16]])
        return vectors


def make_entity(entity_id: str, title: str, project_id: str = "proj1") -> EntityOut:
    return EntityOut(
        id=entity_id,
        project_id=project_id,
        type="npc",
        title=title,
        fields=[
            EntityFieldOut(key="role", field_type=FieldType.TEXT, value="blacksmith"),
            EntityFieldOut(
                key="tags", field_type=FieldType.TAG, value=["ally", "guild"]
            ),
        ],
        icon=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_entity_to_text_flattens_fields() -> None:
    text = entity_to_text(make_entity("e1", "Мира Кузнец"))
    assert "Мира Кузнец (npc)" in text
    assert "role: blacksmith" in text
    assert "tags: ally, guild" in text


def test_entity_to_text_extracts_rich_text() -> None:
    entity = make_entity("e1", "Мира")
    entity.fields.append(
        EntityFieldOut(
            key="bio",
            field_type=FieldType.RICH_TEXT,
            value={
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Кузнец из Норвинтера"}],
                    }
                ],
            },
        )
    )
    assert "Кузнец из Норвинтера" in entity_to_text(entity)


@pytest.mark.asyncio
async def test_index_query_and_remove(tmp_path: Path) -> None:
    index = VectorIndex(ChromaVectorStore(tmp_path / "chroma", FakeEmbedder()))
    entity = make_entity("e1", "Мира Кузнец")
    await index.index_entity(entity)

    # Querying with the entity's own text must return it as the top hit.
    results = await index.query("proj1", entity_to_text(entity), k=1)
    assert results and results[0].entity_id == "e1"

    await index.remove_entity("proj1", "e1")
    assert await index.query("proj1", "кузнец", k=1) == []


@pytest.mark.asyncio
async def test_project_isolation(tmp_path: Path) -> None:
    index = VectorIndex(ChromaVectorStore(tmp_path / "chroma", FakeEmbedder()))
    entity = make_entity("e1", "Мира", project_id="proj1")
    await index.index_entity(entity)
    # The same query against another project's collection sees nothing.
    assert await index.query("proj2", entity_to_text(entity), k=5) == []


@pytest.mark.asyncio
async def test_drop_project(tmp_path: Path) -> None:
    index = VectorIndex(ChromaVectorStore(tmp_path / "chroma", FakeEmbedder()))
    await index.index_entity(make_entity("e1", "Мира"))
    await index.drop_project("proj1")
    assert await index.query("proj1", "Мира", k=5) == []
