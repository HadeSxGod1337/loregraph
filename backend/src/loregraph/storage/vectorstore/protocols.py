from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class LoreChunk:
    entity_id: str
    text: str


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
