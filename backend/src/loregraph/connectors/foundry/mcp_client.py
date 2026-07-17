"""MCP client for a locally running Foundry MCP Bridge.

Loregraph is the MCP *client* here (the inverse of loregraph.mcp_server):
it spawns the bridge's stdio server (adambdooley/foundry-vtt-mcp), which
talks WebSocket to the Foundry module on localhost. One long-lived session
per connection, cached in ConnectorRuntime for the app's lifetime.
"""

import asyncio
import json
import logging
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from loregraph.exceptions import ConnectorUnavailableError

logger = logging.getLogger(__name__)


class FoundryMcpClient:
    """Thin wrapper: spawn, initialize, call tools with a timeout, translate
    every transport failure into ConnectorUnavailableError (502) so callers
    never see raw MCP/anyio exceptions."""

    def __init__(
        self,
        connection_name: str,
        command: str,
        args: list[str],
        env: dict[str, str] | None,
        timeout_s: float,
    ) -> None:
        self._connection_name = connection_name
        self._command = command
        self._args = args
        self._env = env
        self._timeout_s = timeout_s
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tool_names: frozenset[str] | None = None

    async def start(self) -> None:
        stack = AsyncExitStack()
        try:
            async with asyncio.timeout(self._timeout_s):
                read, write = await stack.enter_async_context(
                    stdio_client(
                        StdioServerParameters(
                            command=self._command, args=self._args, env=self._env
                        )
                    )
                )
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
        except asyncio.CancelledError:
            await stack.aclose()
            raise
        except Exception as e:
            await stack.aclose()
            raise ConnectorUnavailableError(
                self._connection_name, f"failed to start Foundry MCP bridge: {e}"
            ) from e
        self._stack = stack
        self._session = session

    async def aclose(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
            self._session = None

    async def tool_names(self) -> frozenset[str]:
        if self._tool_names is None:
            session = self._require_session()
            try:
                async with asyncio.timeout(self._timeout_s):
                    listed = await session.list_tools()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                raise ConnectorUnavailableError(
                    self._connection_name, f"list_tools failed: {e}"
                ) from e
            self._tool_names = frozenset(tool.name for tool in listed.tools)
        return self._tool_names

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a bridge tool and return its text content, JSON-decoded when
        possible. Tool-level errors (isError) and transport failures both
        raise ConnectorUnavailableError — for this connector the distinction
        doesn't change what the caller can do."""
        session = self._require_session()
        try:
            async with asyncio.timeout(self._timeout_s):
                result = await session.call_tool(name, arguments)
        except asyncio.CancelledError:
            raise
        except ConnectorUnavailableError:
            raise
        except Exception as e:
            raise ConnectorUnavailableError(
                self._connection_name, f"tool {name!r} failed: {e}"
            ) from e
        text = _content_text(result.content)
        if getattr(result, "isError", False):
            raise ConnectorUnavailableError(
                self._connection_name, f"tool {name!r} returned an error: {text[:300]}"
            )
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return text

    def _require_session(self) -> ClientSession:
        if self._session is None:
            raise ConnectorUnavailableError(
                self._connection_name, "MCP session is not started"
            )
        return self._session


def _content_text(content: list[Any]) -> str:
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts)
