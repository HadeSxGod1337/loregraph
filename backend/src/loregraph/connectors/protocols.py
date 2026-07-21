from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

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
CAPABILITY_MCP_TOOLS = "mcp_tools"
CAPABILITY_INGEST = "ingest"


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
    write through EntityService/EdgeService (the single write path).

    This is the SYNC half of the story: a deterministic round-trip of
    Loregraph's own export format, provenance-linked (ConnectionEntityLink)
    so a second run updates instead of duplicating. For bringing in a
    project Loregraph never created, see IngestSource below — the two
    coexist on purpose and answer different questions."""

    async def import_data(self, request: ImportRequest) -> ImportResult: ...


@dataclass(frozen=True)
class IngestDocument:
    """One unit of raw external content for the AI migration pipeline (a
    journal page, an actor sheet, a vault note) — plain text/markdown that
    the extractor windows and reads. `external_id` is provenance (which
    external record it came from); `kind` is informational."""

    external_id: str
    title: str
    text: str
    kind: str


@runtime_checkable
class IngestSource(Protocol):
    """Yields the connection's OWN content as plain-text documents for the AI
    migration pipeline (agent/import_graph.py) to extract a graph from.

    Deliberately distinct from Importer: Importer is a deterministic
    round-trip of Loregraph's own export format (idempotent, provenance-
    linked); IngestSource hands RAW external content to the AI extractor, for
    migrating a project Loregraph never created. Migration is one-
    directional and always passes through the same human review as file
    import — it never writes canon directly."""

    async def ingest_documents(self) -> list[IngestDocument]: ...


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


@dataclass(frozen=True)
class RawMcpTool:
    """One tool exactly as its MCP server describes it — name, description,
    and JSON Schema verbatim, no Loregraph-side reinterpretation. This is
    what makes McpToolSource generic: the model sees the server's own
    tool surface and decides how to use it, instead of a hand-written
    Python method per tool per server."""

    name: str
    description: str
    input_schema: dict[str, Any]


@runtime_checkable
class McpToolSource(Protocol):
    """A connection that hands the agent an MCP server's tools directly,
    verbatim, rather than through a curated Python API (contrast
    LiveSource's fixed query(query, kind) shape). The game master connects
    any MCP server they trust — same model as connecting one to an AI
    coding agent — and the assistant gets to call its tools with no
    per-tool Loregraph code. Never Loregraph's own canon: writes here have
    no human_review gate, because they land in the external tool, not the
    world graph."""

    async def list_mcp_tools(self) -> list[RawMcpTool]: ...
    async def call_mcp_tool(self, name: str, arguments: dict[str, Any]) -> str: ...
