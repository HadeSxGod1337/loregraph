"""Lore search's ranking contour, with a fake dense side.

The point under test is that lexical and dense retrieval each rescue what the
other misses — in particular that a name the embedder ranked nowhere still
comes back, which is the failure no embedding-model swap could fix.
"""

from datetime import UTC, datetime

import pytest

from loregraph.schemas.entity import EntityFieldOut, EntityOut, FieldType
from loregraph.services.lore_search import search_lore
from loregraph.storage.vectorstore.protocols import RetrievedChunk

PROJECT_ID = "p1"
_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _entity(entity_id: str, entity_type: str, title: str, **fields: str) -> EntityOut:
    return EntityOut(
        id=entity_id,
        project_id=PROJECT_ID,
        type=entity_type,
        title=title,
        fields=[
            EntityFieldOut(key=key, field_type=FieldType.TEXT, value=value)
            for key, value in fields.items()
        ],
        icon=None,
        created_at=_NOW,
        updated_at=_NOW,
    )


class FakeEntityStore:
    """Only list_entities is exercised — search never needs the write side."""

    def __init__(self, entities: list[EntityOut]) -> None:
        self._entities = entities

    async def list_entities(
        self, project_id: str, entity_type: str | None = None
    ) -> list[EntityOut]:
        return [
            entity
            for entity in self._entities
            if entity.project_id == project_id
            and (entity_type is None or entity.type == entity_type)
        ]


class FakeVectorIndex:
    """Returns a fixed ranking, ignoring the query — so a test can state
    exactly what dense retrieval did and did not surface."""

    def __init__(self, ranking: list[str]) -> None:
        self.ranking = ranking
        self.queried_k: list[int] = []

    async def query(
        self, project_id: str, text: str, k: int = 5
    ) -> list[RetrievedChunk]:
        self.queried_k.append(k)
        return [
            RetrievedChunk(entity_id=entity_id, text="", score=1.0)
            for entity_id in self.ranking[:k]
        ]


async def _search(
    entities: list[EntityOut],
    query: str,
    *,
    dense: list[str] | None = None,
    limit: int = 5,
    entity_type: str | None = None,
) -> list[str]:
    result = await search_lore(
        vector_index=FakeVectorIndex(dense) if dense is not None else None,  # type: ignore[arg-type]
        entity_store=FakeEntityStore(entities),  # type: ignore[arg-type]
        project_id=PROJECT_ID,
        query=query,
        limit=limit,
        entity_type=entity_type,
    )
    return [entity.id for entity in result.entities]


@pytest.mark.asyncio
async def test_exact_name_surfaces_when_dense_never_returned_it() -> None:
    """The core regression: dense retrieval ranks three unrelated entities
    above the one actually named in the query."""
    entities = [
        _entity("npc_egor", "npc", "Егор", bio="Молодой маг-артефактор."),
        _entity("npc_a", "npc", "Мира Кузнец", bio="Кузнец."),
        _entity("npc_b", "npc", "Илья Трактирщик", bio="Трактирщик."),
        _entity("npc_c", "npc", "Виктор", bio="Торговец."),
    ]

    ranked = await _search(entities, "Егор", dense=["npc_a", "npc_b", "npc_c"], limit=4)

    assert "npc_egor" in ranked


@pytest.mark.asyncio
async def test_lexical_match_tolerates_russian_inflection() -> None:
    """«сколько егоров» must still reach the entity titled «Егор» — prefix
    agreement standing in for a stemmer we deliberately do not ship."""
    entities = [
        _entity("npc_egor", "npc", "Егор"),
        _entity("npc_other", "npc", "Мира"),
    ]

    ranked = await _search(entities, "сколько егоров в мире")

    assert ranked == ["npc_egor"]


@pytest.mark.asyncio
async def test_dense_hit_survives_without_any_lexical_overlap() -> None:
    """Meaning-based retrieval must not be crowded out by the lexical side:
    nothing here shares a word with the query."""
    entities = [
        _entity("loc_forge", "location", "Кузница", bio="Здесь чинят доспехи."),
        _entity("npc_a", "npc", "Мира", bio="Кузнец."),
    ]

    ranked = await _search(entities, "где починить снаряжение", dense=["loc_forge"])

    assert ranked[0] == "loc_forge"


@pytest.mark.asyncio
async def test_type_filter_excludes_other_types_from_both_contours() -> None:
    entities = [
        _entity("npc_order", "npc", "Егор из ордена"),
        _entity("fac_order", "faction", "Орден Егора"),
    ]

    ranked = await _search(
        entities, "Егор", dense=["npc_order", "fac_order"], entity_type="faction"
    )

    assert ranked == ["fac_order"]


@pytest.mark.asyncio
async def test_total_counts_matches_before_truncation() -> None:
    entities = [_entity(f"npc_{i}", "npc", f"Егор {i}") for i in range(7)]

    result = await search_lore(
        vector_index=None,
        entity_store=FakeEntityStore(entities),  # type: ignore[arg-type]
        project_id=PROJECT_ID,
        query="Егор",
        limit=3,
    )

    assert len(result.entities) == 3
    assert result.total == 7


@pytest.mark.asyncio
async def test_no_match_returns_nothing_rather_than_filler() -> None:
    entities = [_entity("npc_a", "npc", "Мира", bio="Кузнец.")]

    result = await search_lore(
        vector_index=None,
        entity_store=FakeEntityStore(entities),  # type: ignore[arg-type]
        project_id=PROJECT_ID,
        query="дракон",
        limit=5,
    )

    assert result.entities == []
    assert result.total == 0


@pytest.mark.asyncio
async def test_other_projects_entities_are_never_searched() -> None:
    mine = _entity("npc_mine", "npc", "Егор")
    theirs = _entity("npc_theirs", "npc", "Егор").model_copy(
        update={"project_id": "p2"}
    )

    ranked = await _search([mine, theirs], "Егор")

    assert ranked == ["npc_mine"]


@pytest.mark.asyncio
async def test_typed_query_overfetches_dense_candidates() -> None:
    """A type filter drops dense hits; without over-fetching, a typed search
    would quietly return fewer results than asked for."""
    index = FakeVectorIndex(["npc_a"])
    await search_lore(
        vector_index=index,  # type: ignore[arg-type]
        entity_store=FakeEntityStore([_entity("npc_a", "npc", "Егор")]),  # type: ignore[arg-type]
        project_id=PROJECT_ID,
        query="Егор",
        limit=5,
        entity_type="npc",
    )

    assert index.queried_k == [10]
