import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from loregraph.schemas.entity import EntityFieldOut, EntityOut, FieldType
from loregraph.services.vector_index import (
    VectorIndex,
    entity_chunk_texts,
    entity_to_text,
)
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


def test_entity_to_text_includes_entity_link_labels() -> None:
    """entityLink labels (wikilinks) must appear in vector-embeddable text."""
    entity = make_entity("e1", "Мира")
    entity.fields.append(
        EntityFieldOut(
            key="workplace",
            field_type=FieldType.RICH_TEXT,
            value={
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": "Works at "},
                            {
                                "type": "entityLink",
                                "attrs": {
                                    "entityId": "loc_001",
                                    "fieldKey": None,
                                    "label": "The Iron Forge",
                                },
                            },
                        ],
                    }
                ],
            },
        )
    )
    text = entity_to_text(entity)
    assert "The Iron Forge" in text


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


def _long_entity(entity_id: str, title: str, tail_fact: str) -> EntityOut:
    """An entity whose distinguishing fact sits well past the local embedder's
    ~128-token input window — the case one-chunk-per-entity dropped silently."""
    return EntityOut(
        id=entity_id,
        project_id="proj1",
        type="npc",
        title=title,
        fields=[
            EntityFieldOut(
                key="bio",
                field_type=FieldType.TEXT,
                value=" ".join(["Обычная строка биографии."] * 60),
            ),
            EntityFieldOut(key="secret", field_type=FieldType.TEXT, value=tail_fact),
        ],
        icon=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_entity_to_text_includes_boolean_fields() -> None:
    """Booleans had no `case` arm at all, so they never reached the index."""
    entity = make_entity("e1", "Мира").model_copy(
        update={
            "fields": [
                EntityFieldOut(
                    key="is_alive", field_type=FieldType.BOOLEAN, value=False
                )
            ]
        }
    )
    assert "is_alive: False" in entity_to_text(entity)


def test_short_entity_stays_a_single_chunk() -> None:
    assert len(entity_chunk_texts(make_entity("e1", "Мира"))) == 1


def test_long_entity_is_split_and_every_chunk_names_it() -> None:
    chunks = entity_chunk_texts(_long_entity("e1", "Мира Кузнец", "Тайный ключ."))
    assert len(chunks) > 1
    # Without the repeated head, a tail chunk is unreachable by the name of
    # the character it describes.
    assert all(chunk.startswith("Мира Кузнец (npc)") for chunk in chunks)
    assert any("Тайный ключ." in chunk for chunk in chunks)
    assert all(len(chunk) <= 500 for chunk in chunks)


@pytest.mark.asyncio
async def test_tail_of_a_long_entity_is_retrievable(tmp_path: Path) -> None:
    index = VectorIndex(ChromaVectorStore(tmp_path / "chroma", FakeEmbedder()))
    entity = _long_entity("e1", "Мира Кузнец", "Хранит ключ от подземелья.")
    await index.index_entity(entity)

    # FakeEmbedder matches on exact text, so querying the tail chunk verbatim
    # only works if that chunk was embedded separately at all.
    tail = next(c for c in entity_chunk_texts(entity) if "подземелья" in c)
    results = await index.query("proj1", tail, k=1)

    assert [chunk.entity_id for chunk in results] == ["e1"]


@pytest.mark.asyncio
async def test_one_entity_never_occupies_more_than_one_result_slot(
    tmp_path: Path,
) -> None:
    """Chunks rank, entities are returned: a long entity must not push every
    other entity out of the top-k with its own slices."""
    index = VectorIndex(ChromaVectorStore(tmp_path / "chroma", FakeEmbedder()))
    await index.index_entity(_long_entity("e1", "Мира Кузнец", "Ключ."))
    await index.index_entity(make_entity("e2", "Илья"))

    results = await index.query("proj1", entity_to_text(make_entity("e2", "Илья")), k=5)

    ids = [chunk.entity_id for chunk in results]
    assert len(ids) == len(set(ids))
    assert "e2" in ids


@pytest.mark.asyncio
async def test_removing_an_entity_removes_all_of_its_chunks(tmp_path: Path) -> None:
    index = VectorIndex(ChromaVectorStore(tmp_path / "chroma", FakeEmbedder()))
    entity = _long_entity("e1", "Мира Кузнец", "Ключ от подземелья.")
    await index.index_entity(entity)

    await index.remove_entity("proj1", "e1")

    tail = next(c for c in entity_chunk_texts(entity) if "подземелья" in c)
    assert await index.query("proj1", tail, k=5) == []


@pytest.mark.asyncio
async def test_reindex_returns_entity_count_not_chunk_count(tmp_path: Path) -> None:
    class OneProjectEntityStore:
        async def list_entities(
            self, project_id: str, entity_type: str | None = None
        ) -> list[EntityOut]:
            return [_long_entity("e1", "Мира", "Ключ."), make_entity("e2", "Илья")]

    index = VectorIndex(ChromaVectorStore(tmp_path / "chroma", FakeEmbedder()))
    indexed = await index.reindex_project(OneProjectEntityStore(), "proj1")  # type: ignore[arg-type]

    assert indexed == 2


@pytest.mark.asyncio
async def test_collection_is_stale_when_the_embedder_changed(tmp_path: Path) -> None:
    """The condition a fastembed upgrade creates: same data on disk, an id
    the current process no longer matches. It must be reportable WITHOUT the
    repair path dropping the collection first, or startup can never warn."""

    class OtherEmbedder(FakeEmbedder):
        model_id = "fake-embedder-v2"

    store = ChromaVectorStore(tmp_path / "chroma", FakeEmbedder())
    await VectorIndex(store).index_entity(make_entity("e1", "Мира"))
    assert store.collection_is_stale("proj1") is False

    upgraded = ChromaVectorStore(tmp_path / "chroma", OtherEmbedder())
    assert upgraded.collection_is_stale("proj1") is True


def test_never_indexed_project_is_not_reported_stale(tmp_path: Path) -> None:
    """ "Nothing indexed yet" must not be mistaken for "needs a reindex"."""
    store = ChromaVectorStore(tmp_path / "chroma", FakeEmbedder())
    assert store.collection_is_stale("proj1") is False
