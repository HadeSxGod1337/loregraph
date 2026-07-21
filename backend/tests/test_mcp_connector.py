"""GenericMcpConnector against a fake stdio client — the universal MCP
passthrough (any server, not just Foundry's bridge): the connector exposes
whatever tools the server reports, verbatim, optionally filtered by an
allowlist, with graceful degradation when the server is offline."""

from typing import Any, cast

import pytest

import loregraph.connectors.mcp.connector as mcp_connector_module
from loregraph.connectors.context import ConnectorContext
from loregraph.connectors.mcp.connector import GenericMcpConnector, McpConfig
from loregraph.connectors.mcp.stdio_client import McpToolInfo
from loregraph.exceptions import ConnectorUnavailableError


class FakeMcpStdioClient:
    """Stands in for McpStdioClient: records calls, serves canned tools."""

    fail_start = False

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def start(self) -> None:
        if FakeMcpStdioClient.fail_start:
            raise ConnectorUnavailableError("Test", "server did not start")

    async def aclose(self) -> None:
        pass

    async def list_tools(self) -> list[McpToolInfo]:
        return [
            McpToolInfo(
                name="roll-dice",
                description="Roll a die.",
                input_schema={
                    "type": "object",
                    "properties": {"sides": {"type": "integer"}},
                    "required": ["sides"],
                },
            ),
            McpToolInfo(
                name="move-token",
                description="Move a token on the scene.",
                input_schema={"type": "object", "properties": {}},
            ),
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((name, arguments))
        if name == "roll-dice":
            return {"result": 4}
        return {"ok": True}


@pytest.fixture(autouse=True)
def fake_mcp(monkeypatch: pytest.MonkeyPatch) -> type[FakeMcpStdioClient]:
    FakeMcpStdioClient.fail_start = False
    monkeypatch.setattr(mcp_connector_module, "McpStdioClient", FakeMcpStdioClient)
    return FakeMcpStdioClient


def _make_connector(allowed_tools: list[str] | None = None) -> GenericMcpConnector:
    context = ConnectorContext(
        project_id="p1",
        connection_id="c1",
        connection_name="My Dice Server",
        entity_service=cast(Any, None),
        edge_service=cast(Any, None),
        entity_store=cast(Any, None),
        edge_store=cast(Any, None),
        attachment_store=cast(Any, None),
        attachments_dir=cast(Any, None),
        link_store=cast(Any, None),
        runtime=None,
    )
    return GenericMcpConnector(
        McpConfig(command="node", args=["server.js"], allowed_tools=allowed_tools),
        context,
    )


@pytest.mark.asyncio
async def test_list_mcp_tools_returns_every_tool_verbatim_by_default() -> None:
    connector = _make_connector()

    tools = await connector.list_mcp_tools()

    names = {tool.name for tool in tools}
    assert names == {"roll-dice", "move-token"}
    roll = next(tool for tool in tools if tool.name == "roll-dice")
    assert roll.description == "Roll a die."
    assert roll.input_schema["required"] == ["sides"]


@pytest.mark.asyncio
async def test_list_mcp_tools_respects_allowlist() -> None:
    connector = _make_connector(allowed_tools=["roll-dice"])

    tools = await connector.list_mcp_tools()

    assert {tool.name for tool in tools} == {"roll-dice"}


@pytest.mark.asyncio
async def test_call_mcp_tool_passes_through_the_result() -> None:
    connector = _make_connector()

    result = await connector.call_mcp_tool("roll-dice", {"sides": 20})

    assert "4" in result


@pytest.mark.asyncio
async def test_call_mcp_tool_blocks_a_tool_outside_the_allowlist() -> None:
    connector = _make_connector(allowed_tools=["roll-dice"])

    result = await connector.call_mcp_tool("move-token", {})

    assert "not in this connection's allowed tool list" in result


@pytest.mark.asyncio
async def test_test_connection_reports_unreachable_without_raising() -> None:
    FakeMcpStdioClient.fail_start = True
    connector = _make_connector()

    probe = await connector.test_connection()

    assert probe.ok is False
    assert probe.detail_code == "mcp_unreachable"


@pytest.mark.asyncio
async def test_test_connection_reports_tool_count() -> None:
    connector = _make_connector()

    probe = await connector.test_connection()

    assert probe.ok is True
    assert probe.info["tool_count"] == "2"
