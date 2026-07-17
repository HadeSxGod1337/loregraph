from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from loregraph.schemas.connection import (
    ExportPreview,
    ExportRequest,
    ExportResult,
    ImportRequest,
    ImportResult,
    ProbeResult,
)

# Capability names reported by GET /api/connectors and stored on descriptors.
CAPABILITY_EXPORT = "export"
CAPABILITY_IMPORT = "import"
CAPABILITY_LIVE = "live"


@dataclass(frozen=True)
class ExternalChunk:
    """One piece of external data returned by a LiveSource query — reference
    material for the agent (chat answers, grounding), never persisted and
    never a valid grounding citation target."""

    source_name: str
    connector_type: str
    kind: str
    title: str
    text: str


@runtime_checkable
class Exporter(Protocol):
    """Pushes Loregraph canon into the external tool."""

    async def preview_export(self, request: ExportRequest) -> ExportPreview: ...
    async def export(self, request: ExportRequest) -> ExportResult: ...


@runtime_checkable
class Importer(Protocol):
    """Pulls external data into Loregraph entities. Implementations must
    write through EntityService/EdgeService (the single write path)."""

    async def import_data(self, request: ImportRequest) -> ImportResult: ...


@runtime_checkable
class LiveSource(Protocol):
    """On-demand read access for the agent, without importing into canon."""

    async def query(
        self, query: str, kind: str | None = None
    ) -> list[ExternalChunk]: ...


@runtime_checkable
class ConnectionProbe(Protocol):
    """Cheap 'is this connection set up correctly' check for the UI."""

    async def test_connection(self) -> ProbeResult: ...
