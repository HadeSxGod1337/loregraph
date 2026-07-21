"""Universal MCP passthrough: unlike FoundryConnector (a curated Exporter/
Importer/LiveSource for one specific bridge), this connector makes no
assumption about what the connected server does. It exposes the server's
own tools to the agent verbatim (McpToolSource) — the model sees each
tool's real name/description/schema and decides how to use it, exactly
like connecting an MCP server to any other AI agent.

This is a deliberate scope boundary: Loregraph's own canon (the world
graph) is never touched by this connector — that always goes through
propose_lore/edit_entity and human_review. A generic MCP server's tools
execute immediately with no review gate, because they act on the *external*
tool, not on Loregraph's canon (see McpToolSource's docstring).
"""

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from loregraph.connectors.context import ConnectorContext
from loregraph.connectors.mcp.stdio_client import McpStdioClient
from loregraph.connectors.protocols import RawMcpTool
from loregraph.exceptions import ConnectorUnavailableError
from loregraph.schemas.connection import ProbeResult

logger = logging.getLogger(__name__)

# A misbehaving tool could return an arbitrarily large payload; this keeps
# any single result from blowing out the next assistant call's prompt.
_RESULT_TEXT_LIMIT = 4000


class McpConfig(BaseModel):
    command: str = Field(description="Executable to spawn, e.g. 'node' or 'npx'.")
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] | None = None
    request_timeout_s: float = 15.0
    # None/empty = every tool the server exposes is available — the same
    # trust model as connecting an MCP server directly to an AI agent: the
    # game master is the one who chose to run this server. A non-empty list
    # restricts the agent to exactly those tool names (e.g. to keep a
    # live-session action like moving a token out of the agent's reach
    # without needing Loregraph code changes to enforce it).
    allowed_tools: list[str] | None = None


class GenericMcpConnector:
    """Implements McpToolSource and ConnectionProbe."""

    def __init__(self, config: McpConfig, context: ConnectorContext) -> None:
        self._config = config
        self._context = context

    async def _client(self) -> McpStdioClient:
        runtime = self._context.runtime
        config = self._config

        async def factory() -> McpStdioClient:
            client = McpStdioClient(
                connection_name=self._context.connection_name,
                command=config.command,
                args=list(config.args),
                env=config.env,
                timeout_s=config.request_timeout_s,
            )
            await client.start()
            return client

        if runtime is None:
            # No runtime (unit-test context): a throwaway client still works,
            # it just won't be reused.
            return await factory()
        return await runtime.get_or_create(self._context.connection_id, factory)

    # ── probe ────────────────────────────────────────────────────────────────

    async def test_connection(self) -> ProbeResult:
        try:
            client = await self._client()
            tools = await client.list_tools()
        except ConnectorUnavailableError as e:
            return ProbeResult(
                ok=False, detail_code="mcp_unreachable", info={"error": str(e)}
            )
        return ProbeResult(
            ok=True, detail_code="mcp_ok", info={"tool_count": str(len(tools))}
        )

    # ── McpToolSource ────────────────────────────────────────────────────────

    async def list_mcp_tools(self) -> list[RawMcpTool]:
        client = await self._client()
        tools = await client.list_tools()
        allowed = self._config.allowed_tools
        if allowed:
            allowed_set = set(allowed)
            tools = [tool for tool in tools if tool.name in allowed_set]
        return [
            RawMcpTool(
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema,
            )
            for tool in tools
        ]

    async def call_mcp_tool(self, name: str, arguments: dict[str, Any]) -> str:
        allowed = self._config.allowed_tools
        if allowed and name not in allowed:
            return f"Tool {name!r} is not in this connection's allowed tool list."
        client = await self._client()
        result = await client.call_tool(name, arguments)
        text = (
            result
            if isinstance(result, str)
            else json.dumps(result, ensure_ascii=False)
        )
        return text[:_RESULT_TEXT_LIMIT]
