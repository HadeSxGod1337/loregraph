from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class LoreChunk:
    """One embeddable slice of one entity.

    `entity_id` is the *entity*, not the chunk — several chunks share it when
    an entity is too long to embed in one piece. Callers address entities, so
    upsert/delete/query all stay entity-keyed; how a store lays chunks out
    internally is its own business (see storage/vectorstore/chroma_store.py).
    """

    entity_id: str
    text: str
    chunk_index: int = 0


@dataclass(frozen=True)
class RetrievedChunk:
    entity_id: str
    text: str
    score: float


@runtime_checkable
class VectorStore(Protocol):
    """Semantic index over entity text, hard-isolated per project.

    Derived data only: SQLite is the source of truth and any collection can
    be rebuilt from it (see docs/agent_architecture.md, section 4)."""

    async def upsert(self, project_id: str, chunks: Sequence[LoreChunk]) -> None: ...
    async def delete(self, project_id: str, entity_ids: Sequence[str]) -> None: ...
    async def query(
        self, project_id: str, text: str, k: int = 5
    ) -> list[RetrievedChunk]: ...
    async def drop_project(self, project_id: str) -> None: ...


@runtime_checkable
class IndexHealth(Protocol):
    """Optional capability: can this store tell whether what it persisted is
    still readable by the current configuration?

    Deliberately separate from VectorStore rather than bolted onto it (ISP): a
    store with no on-disk format of its own has nothing to answer, and callers
    check for the capability instead of every implementation having to fake
    it.
    """

    def collection_is_stale(self, project_id: str) -> bool: ...
