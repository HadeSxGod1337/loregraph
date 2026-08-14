"""Store doubles for tests that exercise one node in isolation.

Nodes that only read get a fake here instead of a database fixture; the
pipeline-level tests (test_agent_graph.py, test_agent_relationships.py) use
the real sqlite stores, so the contract itself stays covered by them.
"""

from collections.abc import Sequence

from loregraph.schemas.edge import EdgeCreate, EdgeOut, EdgeUpdate
from loregraph.schemas.entity import (
    EntityCreate,
    EntityOut,
    EntityPatch,
    EntityPlayerViewUpdate,
    EntityPositionEntry,
    EntityUpdate,
)
from loregraph.storage.vectorstore.protocols import RetrievedChunk


class FixedVectorIndex:
    """Returns a fixed hit list for every query.

    Retrieval decides which entities the model may reference, and
    verify_grounding then holds the draft to exactly that set — so seeding
    this is how a test says "these are the entities the run was shown"."""

    def __init__(self, entity_ids: list[str]) -> None:
        self._entity_ids = entity_ids

    async def query(
        self, project_id: str, text: str, k: int = 5
    ) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(entity_id=entity_id, text="", score=1.0)
            for entity_id in self._entity_ids[:k]
        ]


class EmptyEntityStore:
    """An EntityStore over an empty world.

    For node-in-isolation tests where "does this title clone an existing
    entity" is noise — validate_changes runs a dedup pass over
    list_entities(), and an empty world means no false duplicate ever fires.
    Reads that must return something (get_many) return nothing; writes raise."""

    def __init__(self, entities: list[EntityOut] | None = None) -> None:
        self._entities = entities or []

    async def list_entities(
        self, project_id: str, entity_type: str | None = None
    ) -> list[EntityOut]:
        return [
            e
            for e in self._entities
            if e.project_id == project_id
            and (entity_type is None or e.type == entity_type)
        ]

    async def get_many(self, entity_ids: Sequence[str]) -> list[EntityOut]:
        wanted = set(entity_ids)
        return [e for e in self._entities if e.id in wanted]

    async def list_entity_types(self, project_id: str) -> list[str]:
        return []

    async def exists(self, entity_id: str) -> bool:
        return any(e.id == entity_id for e in self._entities)

    async def get(self, entity_id: str) -> EntityOut:
        raise NotImplementedError

    async def create(self, data: EntityCreate, project_id: str) -> EntityOut:
        raise NotImplementedError

    async def update(self, entity_id: str, data: EntityUpdate) -> EntityOut:
        raise NotImplementedError

    async def patch(self, entity_id: str, data: EntityPatch) -> EntityOut:
        raise NotImplementedError

    async def delete(self, entity_id: str) -> None:
        raise NotImplementedError

    async def set_icon(self, entity_id: str, attachment_id: str | None) -> EntityOut:
        raise NotImplementedError

    async def set_player_view(
        self, entity_id: str, data: EntityPlayerViewUpdate
    ) -> EntityOut:
        raise NotImplementedError

    async def update_positions(
        self, positions: Sequence[EntityPositionEntry]
    ) -> list[EntityOut]:
        raise NotImplementedError


class EmptyEdgeStore:
    """An EdgeStore over a world with no relationships.

    For tests about something else entirely — verify_grounding's citation and
    endpoint guards, say — where "does this contradict an existing edge" is
    noise. Writes raise: a read-only double that silently accepted them would
    let a test pass while claiming a write path it never had."""

    async def get(self, edge_id: str) -> EdgeOut:
        raise NotImplementedError

    async def list_for_entity(self, entity_id: str) -> list[EdgeOut]:
        return []

    async def list_all(
        self, project_id: str, edge_types: frozenset[str] | None = None
    ) -> list[EdgeOut]:
        return []

    async def create(self, data: EdgeCreate, project_id: str) -> EdgeOut:
        raise NotImplementedError

    async def update(self, edge_id: str, data: EdgeUpdate) -> EdgeOut:
        raise NotImplementedError

    async def delete(self, edge_id: str) -> None:
        raise NotImplementedError
