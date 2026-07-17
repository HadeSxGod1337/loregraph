from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from loregraph.services.edge_service import EdgeService
from loregraph.services.entity_service import EntityService
from loregraph.storage.protocols import (
    AttachmentStore,
    ConnectionEntityLinkStore,
    EdgeStore,
    EntityStore,
)

if TYPE_CHECKING:
    from loregraph.connectors.runtime import ConnectorRuntime


@dataclass(frozen=True)
class ConnectorContext:
    """Everything a connector instance may need, injected at construction.

    Writes go through entity_service/edge_service only (single write path);
    the raw stores are for reads. `runtime` hosts long-lived clients for
    connectors that need them (Foundry MCP sessions) — None in contexts that
    never touch such a connector (e.g. unit tests of file-based ones).
    """

    project_id: str
    connection_id: str
    connection_name: str
    entity_service: EntityService
    edge_service: EdgeService
    entity_store: EntityStore
    edge_store: EdgeStore
    attachment_store: AttachmentStore
    attachments_dir: Path
    link_store: ConnectionEntityLinkStore
    runtime: "ConnectorRuntime | None" = None
