"""Generic MCP tool access for the agent — progressive disclosure (the
ToolSearch pattern), the McpToolSource analog of connectors/live.py's
LiveSourceProvider.

Instead of binding every connected MCP server's tools on every turn (dozens
of full JSON schemas — token-expensive, and so many lookalike tools that the
model picks the wrong one), the assistant binds just two meta-tools:
discover_mcp_tools (find a tool by intent, get its real schema) and
call_mcp_tool (run it by name). This is how Claude Code itself works with
deferred tools — the model searches the catalog on demand rather than
carrying it all in context.

Tools are namespaced under a qualified name (connection + tool, see
qualified_name()) so two connections can expose a tool with the same name
without colliding — the same convention MCP clients use for their prefixes.
"""

import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from loregraph.connectors.protocols import McpToolSource, RawMcpTool

_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def qualified_name(connection_name: str, tool_name: str) -> str:
    slug = _SANITIZE_RE.sub("_", connection_name.strip()) or "mcp"
    return f"mcp__{slug}__{tool_name}"


# --- Meta-tool schemas (bound instead of every MCP tool) --------------------
# These two ARE the only MCP-related schemas the assistant model ever sees,
# no matter how many servers/tools are connected. Their docstrings are the
# tool descriptions the model reads.


class discover_mcp_tools(BaseModel):
    """Find tools exposed by the connected MCP servers (listed in
    <mcp_connections>). Those servers' tools are NOT bound directly — call
    this FIRST whenever the game master's request is about a connected
    external tool. Returns each matching tool's exact name, description, and
    input schema so you can then run it with call_mcp_tool. Leave query empty
    to browse the whole catalog by name."""

    query: str = Field(
        default="",
        description="What you want to do, in plain words (e.g. 'read a "
        "journal page's full text', 'list world items'). Empty lists every "
        "available tool by name so you can pick one.",
    )


class call_mcp_tool(BaseModel):
    """Run a specific MCP tool found via discover_mcp_tools. Executes
    IMMEDIATELY on the external tool with NO game master review — it never
    touches this world's canon graph (that is only ever propose_lore /
    edit_entity). Always report success or failure back to the game master."""

    tool: str = Field(
        description="Exact qualified tool name from discover_mcp_tools, "
        "e.g. 'mcp__my_foundry__list-journals'."
    )
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments object matching that tool's input schema.",
    )


# --- Catalog + lazy provider ------------------------------------------------


@dataclass(frozen=True)
class McpConnection:
    name: str
    connector_type: str
    source: McpToolSource


@dataclass(frozen=True)
class McpToolEntry:
    connection_name: str
    connector_type: str
    tool: RawMcpTool
    source: McpToolSource

    @property
    def qualified_name(self) -> str:
        return qualified_name(self.connection_name, self.tool.name)


class McpToolProvider:
    """Lazy: holds connections only. The tool catalog is fetched (and cached
    for this request) on the first discover/call — a chat turn that never
    touches MCP costs no bridge spawn and no list round-trip."""

    def __init__(self, connections: list[McpConnection]) -> None:
        self._connections = list(connections)
        self._catalog: list[McpToolEntry] | None = None

    def connection_names(self) -> list[str]:
        return [c.name for c in self._connections]

    async def catalog(self) -> list[McpToolEntry]:
        if self._catalog is None:
            entries: list[McpToolEntry] = []
            for conn in self._connections:
                for tool in await conn.source.list_mcp_tools():
                    entries.append(
                        McpToolEntry(
                            connection_name=conn.name,
                            connector_type=conn.connector_type,
                            tool=tool,
                            source=conn.source,
                        )
                    )
            self._catalog = entries
        return self._catalog

    async def find(self, query: str) -> list[McpToolEntry]:
        """Lexical rank of the catalog by query terms against each tool's
        qualified name + description. Empty query returns the whole catalog
        (browse). Deterministic, no embeddings — cheap and predictable, and
        the model refines its own query when the first shortlist isn't right."""
        entries = await self.catalog()
        terms = [t for t in re.split(r"\W+", query.lower()) if t]
        if not terms:
            return entries
        scored: list[tuple[int, McpToolEntry]] = []
        for entry in entries:
            haystack = f"{entry.qualified_name} {entry.tool.description}".lower()
            score = sum(haystack.count(term) for term in terms)
            if score:
                scored.append((score, entry))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [entry for _, entry in scored]

    async def call(self, qualified: str, arguments: dict[str, Any]) -> str:
        for entry in await self.catalog():
            if entry.qualified_name == qualified:
                return await entry.source.call_mcp_tool(entry.tool.name, arguments)
        raise KeyError(qualified)

    def __bool__(self) -> bool:
        return bool(self._connections)
