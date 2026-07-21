"""Generic MCP tool sources for the agent — the McpToolSource analog of
connectors/live.py's LiveSourceProvider. Built per request (api/deps.py)
from the project's connections whose connector implements McpToolSource.

Each raw tool is bound to the chat model under a namespaced name
(connection + tool, see qualified_name()) so two connections can expose a
tool with the same name without colliding — the same convention MCP
clients (Claude Code among them) use for their own tool prefixes.
"""

import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, create_model

from loregraph.connectors.protocols import McpToolSource, RawMcpTool

_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9_-]+")
_JSON_SCHEMA_TYPES: dict[str, Any] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def qualified_name(connection_name: str, tool_name: str) -> str:
    slug = _SANITIZE_RE.sub("_", connection_name.strip()) or "mcp"
    return f"mcp__{slug}__{tool_name}"


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
    def __init__(self, entries: list[McpToolEntry]) -> None:
        self._entries = list(entries)

    def entries(self) -> list[McpToolEntry]:
        return list(self._entries)

    def get(self, qualified: str) -> McpToolEntry | None:
        for entry in self._entries:
            if entry.qualified_name == qualified:
                return entry
        return None

    def __bool__(self) -> bool:
        return bool(self._entries)


def _json_schema_type(property_schema: dict[str, Any]) -> Any:
    json_type = property_schema.get("type")
    if isinstance(json_type, list):
        json_type = next((t for t in json_type if t != "null"), None)
    if not isinstance(json_type, str):
        return Any
    return _JSON_SCHEMA_TYPES.get(json_type, Any)


def build_tool_model(entry: McpToolEntry) -> type[BaseModel]:
    """A Pydantic model reflecting the tool's own JSON Schema verbatim —
    built fresh per turn from RawMcpTool.input_schema, not written by hand
    per tool. This is what lets an arbitrary MCP server's tools bind to the
    chat model (chat_model.bind_tools()) the same way the assistant's own
    hand-written tool schemas do (see agent/skills/registry.py)."""
    schema = entry.tool.input_schema or {}
    properties = schema.get("properties") if isinstance(schema, dict) else None
    required = set(schema.get("required") or []) if isinstance(schema, dict) else set()
    fields: dict[str, Any] = {}
    if isinstance(properties, dict):
        for name, prop_schema in properties.items():
            if not isinstance(prop_schema, dict) or not name.isidentifier():
                continue
            py_type = _json_schema_type(prop_schema)
            description = prop_schema.get("description")
            if name in required:
                fields[name] = (
                    py_type,
                    Field(description=description) if description else Field(),
                )
            else:
                fields[name] = (
                    py_type | None,
                    Field(default=None, description=description),
                )
    return create_model(
        entry.qualified_name,
        __doc__=entry.tool.description
        or f"Tool from the '{entry.connection_name}' MCP connection.",
        **fields,
    )
