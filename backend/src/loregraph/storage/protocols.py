from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from loregraph.schemas.agent import (
    AgentReviewPayload,
    AgentSessionOut,
    AgentSessionStatus,
)
from loregraph.schemas.attachment import AttachmentOut
from loregraph.schemas.connection import (
    ConnectionCreate,
    ConnectionEntityLinkOut,
    ConnectionOut,
    ConnectionUpdate,
)
from loregraph.schemas.edge import EdgeCreate, EdgeOut, EdgeUpdate
from loregraph.schemas.entity import (
    EntityCreate,
    EntityOut,
    EntityPositionEntry,
    EntityUpdate,
)
from loregraph.schemas.knowledge import KnowledgeSourceOut
from loregraph.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate
from loregraph.schemas.usage import UsageEvent, UsageRollupRow


@runtime_checkable
class ProjectStore(Protocol):
    async def list_projects(self) -> list[ProjectOut]: ...
    async def create(self, data: ProjectCreate) -> ProjectOut: ...
    async def get(self, project_id: str) -> ProjectOut: ...
    async def update(self, project_id: str, data: ProjectUpdate) -> ProjectOut: ...
    async def delete(self, project_id: str) -> None: ...
    async def exists(self, project_id: str) -> bool: ...


@runtime_checkable
class EntityStore(Protocol):
    async def list_entities(
        self, project_id: str, entity_type: str | None = None
    ) -> list[EntityOut]: ...
    async def create(self, data: EntityCreate, project_id: str) -> EntityOut: ...
    async def get(self, entity_id: str) -> EntityOut: ...
    async def get_many(self, entity_ids: Sequence[str]) -> list[EntityOut]: ...
    async def exists(self, entity_id: str) -> bool: ...
    async def update(self, entity_id: str, data: EntityUpdate) -> EntityOut: ...
    async def delete(self, entity_id: str) -> None: ...
    async def set_icon(
        self, entity_id: str, attachment_id: str | None
    ) -> EntityOut: ...
    async def update_positions(
        self, positions: Sequence[EntityPositionEntry]
    ) -> list[EntityOut]: ...


@runtime_checkable
class EdgeStore(Protocol):
    async def get(self, edge_id: str) -> EdgeOut: ...
    async def list_for_entity(self, entity_id: str) -> list[EdgeOut]: ...
    async def list_all(
        self, project_id: str, edge_types: frozenset[str] | None = None
    ) -> list[EdgeOut]: ...
    async def create(self, data: EdgeCreate, project_id: str) -> EdgeOut: ...
    async def update(self, edge_id: str, data: EdgeUpdate) -> EdgeOut: ...
    async def delete(self, edge_id: str) -> None: ...


@runtime_checkable
class AgentSessionStore(Protocol):
    async def create(self, project_id: str, thread_id: str) -> AgentSessionOut: ...
    async def get(self, thread_id: str) -> AgentSessionOut: ...
    async def list_for_project(self, project_id: str) -> list[AgentSessionOut]: ...
    async def update(
        self,
        thread_id: str,
        *,
        status: AgentSessionStatus | None = None,
        title: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        committed_entity_ids: list[str] | None = None,
        review: AgentReviewPayload | None = None,
        clear_review: bool = False,
    ) -> AgentSessionOut: ...


@runtime_checkable
class UsageStore(Protocol):
    """Granular per-call LLM token accounting (per node/model/session/project,
    cache-aware). Written at each call site during a run; read as a project
    rollup for the usage endpoint."""

    async def record(self, event: UsageEvent) -> None: ...
    async def project_rollup(self, project_id: str) -> list[UsageRollupRow]: ...


@runtime_checkable
class AttachmentStore(Protocol):
    async def create(
        self,
        entity_id: str,
        original_filename: str,
        content_type: str,
        content: bytes,
    ) -> AttachmentOut: ...
    async def list_for_entity(self, entity_id: str) -> list[AttachmentOut]: ...
    async def delete(self, attachment_id: str) -> None: ...


@runtime_checkable
class ConnectionStore(Protocol):
    async def list_for_project(self, project_id: str) -> list[ConnectionOut]: ...
    async def create(
        self, project_id: str, data: ConnectionCreate
    ) -> ConnectionOut: ...
    async def get(self, connection_id: str) -> ConnectionOut: ...
    async def update(
        self, connection_id: str, data: ConnectionUpdate
    ) -> ConnectionOut: ...
    async def delete(self, connection_id: str) -> None: ...


@runtime_checkable
class ConnectionEntityLinkStore(Protocol):
    async def upsert(
        self,
        connection_id: str,
        entity_id: str,
        external_id: str,
        external_kind: str,
    ) -> ConnectionEntityLinkOut: ...
    async def list_for_connection(
        self, connection_id: str
    ) -> list[ConnectionEntityLinkOut]: ...
    async def get_by_external(
        self, connection_id: str, external_kind: str, external_id: str
    ) -> ConnectionEntityLinkOut | None: ...
    async def list_for_entity(
        self, connection_id: str, entity_id: str
    ) -> list[ConnectionEntityLinkOut]: ...
    async def delete_for_entity(
        self, connection_id: str, entity_id: str
    ) -> None: ...


@runtime_checkable
class KnowledgeSourceStore(Protocol):
    async def create(
        self,
        project_id: str,
        original_filename: str,
        content_type: str,
        content: bytes,
    ) -> KnowledgeSourceOut: ...
    async def list_for_project(self, project_id: str) -> list[KnowledgeSourceOut]: ...
    async def get(self, source_id: str) -> KnowledgeSourceOut: ...
    async def update_status(
        self,
        source_id: str,
        *,
        status: str,
        error: str | None = None,
        chunk_count: int | None = None,
    ) -> KnowledgeSourceOut: ...
    async def delete(self, source_id: str) -> None: ...
