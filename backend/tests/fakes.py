"""Store doubles for tests that exercise one node in isolation.

Nodes that only read get a fake here instead of a database fixture; the
pipeline-level tests (test_agent_graph.py, test_agent_relationships.py) use
the real sqlite stores, so the contract itself stays covered by them.
"""

from loregraph.schemas.edge import EdgeCreate, EdgeOut, EdgeUpdate
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
