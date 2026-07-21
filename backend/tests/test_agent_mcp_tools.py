"""The agent side of the universal MCP passthrough — progressive disclosure:
qualified naming, discover_mcp_tools (find by intent, get the real schema),
call_mcp_tool (run by name), lazy catalog (no listing until used), and
binding just the two meta-tools. Same invariant as the LiveSource tests: an
offline MCP server degrades gracefully, it never breaks a turn."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from pydantic import ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.agent.mcp_tools import (
    McpConnection,
    McpToolProvider,
    qualified_name,
)
from loregraph.agent.nodes.assistant import assistant
from loregraph.agent.nodes.tools import run_tools
from loregraph.agent.state import AgentState
from loregraph.connectors.protocols import RawMcpTool
from loregraph.exceptions import ConnectorUnavailableError
from loregraph.schemas.project import ProjectCreate
from loregraph.storage.sqlite.db import (
    create_engine_for,
    init_db,
    make_session_factory,
)
from loregraph.storage.sqlite.project_store import SqliteProjectStore

META_TOOL_NAMES = {"discover_mcp_tools", "call_mcp_tool"}


class FakeMcpToolSource:
    def __init__(self, tools: list[RawMcpTool] | None = None) -> None:
        self.tools = tools or [_roll_dice_tool()]
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.list_count = 0

    async def list_mcp_tools(self) -> list[RawMcpTool]:
        self.list_count += 1
        return self.tools

    async def call_mcp_tool(self, name: str, arguments: dict[str, Any]) -> str:
        self.calls.append((name, arguments))
        return f"called {name}"


class OfflineMcpToolSource:
    async def list_mcp_tools(self) -> list[RawMcpTool]:
        raise ConnectorUnavailableError("Dice Server", "connection refused")

    async def call_mcp_tool(self, name: str, arguments: dict[str, Any]) -> str:
        raise ConnectorUnavailableError("Dice Server", "connection refused")


class RecordingChatModel(BaseChatModel):
    """Stands in for the assistant's chat model just to capture which tools
    assistant() actually bound this turn."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    bound_tools: list[Any] = Field(default_factory=list)

    def bind_tools(self, tools: Any, **kwargs: Any) -> Runnable[Any, Any]:
        self.bound_tools = list(tools)
        return self

    def _generate(
        self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage("ok"))])

    @property
    def _llm_type(self) -> str:
        return "recording"


def _roll_dice_tool() -> RawMcpTool:
    return RawMcpTool(
        name="roll-dice",
        description="Roll a die with the given number of sides.",
        input_schema={
            "type": "object",
            "properties": {
                "sides": {"type": "integer", "description": "Number of sides."},
                "label": {"type": "string"},
            },
            "required": ["sides"],
        },
    )


def _list_journals_tool() -> RawMcpTool:
    return RawMcpTool(
        name="list-journals",
        description="List journal entries and read a journal page's full text.",
        input_schema={
            "type": "object",
            "properties": {"journalId": {"type": "string"}},
        },
    )


def _connection(source: object, name: str = "Dice Server") -> McpConnection:
    return McpConnection(
        name=name,
        connector_type="mcp",
        source=source,  # type: ignore[arg-type]
    )


def _tool_call_state(name: str, args: dict[str, Any]) -> AgentState:
    call = {"name": name, "args": args, "id": "call-1"}
    return AgentState(project_id="p1", messages=[AIMessage("", tool_calls=[call])])


async def _run(state: AgentState, provider: McpToolProvider | None) -> str:
    update = await run_tools(
        state,
        vector_index=None,
        knowledge_index=None,
        entity_store=None,  # type: ignore[arg-type]
        mcp_tools=provider,
    )
    return str(update["messages"][0].content)


@pytest_asyncio.fixture
async def db_session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    engine = create_engine_for(tmp_path / "test.sqlite3")
    await init_db(engine)
    session = make_session_factory(engine)()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()


def test_qualified_name_sanitizes_connection_name() -> None:
    assert (
        qualified_name("My Dice Server!", "roll-dice")
        == "mcp__My_Dice_Server___roll-dice"
    )


@pytest.mark.asyncio
async def test_discover_returns_matched_tool_with_its_real_schema() -> None:
    provider = McpToolProvider([_connection(FakeMcpToolSource())])

    content = await _run(
        _tool_call_state("discover_mcp_tools", {"query": "roll a die"}), provider
    )

    assert qualified_name("Dice Server", "roll-dice") in content
    assert "input schema" in content
    assert "sides" in content  # the tool's real schema, verbatim


@pytest.mark.asyncio
async def test_discover_ranks_by_intent_not_by_lookalikes() -> None:
    """The bug this fixes: 'journal' must surface the journals tool, not an
    unrelated one that happens to be bound alongside it."""
    source = FakeMcpToolSource([_roll_dice_tool(), _list_journals_tool()])
    provider = McpToolProvider([_connection(source)])

    content = await _run(
        _tool_call_state("discover_mcp_tools", {"query": "journal page text"}),
        provider,
    )

    first_line = content.splitlines()[0]
    assert "list-journals" in first_line


@pytest.mark.asyncio
async def test_discover_empty_query_browses_whole_catalog() -> None:
    source = FakeMcpToolSource([_roll_dice_tool(), _list_journals_tool()])
    provider = McpToolProvider([_connection(source)])

    content = await _run(
        _tool_call_state("discover_mcp_tools", {"query": ""}), provider
    )

    assert "roll-dice" in content
    assert "list-journals" in content


@pytest.mark.asyncio
async def test_call_mcp_tool_dispatches_to_the_right_connection() -> None:
    source = FakeMcpToolSource()
    provider = McpToolProvider([_connection(source)])
    name = qualified_name("Dice Server", "roll-dice")

    content = await _run(
        _tool_call_state("call_mcp_tool", {"tool": name, "arguments": {"sides": 20}}),
        provider,
    )

    assert "called roll-dice" in content
    assert source.calls == [("roll-dice", {"sides": 20})]


@pytest.mark.asyncio
async def test_call_mcp_tool_offline_yields_message_not_exception() -> None:
    provider = McpToolProvider([_connection(OfflineMcpToolSource())])
    name = qualified_name("Dice Server", "roll-dice")

    content = await _run(
        _tool_call_state("call_mcp_tool", {"tool": name, "arguments": {}}), provider
    )

    assert "unavailable" in content


@pytest.mark.asyncio
async def test_call_mcp_tool_unknown_name_degrades_gracefully() -> None:
    provider = McpToolProvider([_connection(FakeMcpToolSource())])

    content = await _run(
        _tool_call_state("call_mcp_tool", {"tool": "mcp__Ghost__nope"}), provider
    )

    assert "Unknown MCP tool" in content


@pytest.mark.asyncio
async def test_mcp_meta_tools_without_provider_degrade_gracefully() -> None:
    content = await _run(
        _tool_call_state("discover_mcp_tools", {"query": "anything"}), None
    )
    assert "No MCP tool sources are connected" in content


@pytest.mark.asyncio
async def test_provider_is_lazy_and_caches_the_catalog() -> None:
    """Constructing the provider and browsing its connection names must not
    list tools (no bridge spawn on a turn that never touches MCP); the first
    discovery lists once, and the catalog is cached thereafter."""
    source = FakeMcpToolSource()
    provider = McpToolProvider([_connection(source)])

    assert provider.connection_names() == ["Dice Server"]
    assert source.list_count == 0  # naming a connection never lists its tools

    await _run(_tool_call_state("discover_mcp_tools", {"query": "die"}), provider)
    assert source.list_count == 1

    await _run(_tool_call_state("discover_mcp_tools", {"query": "die"}), provider)
    assert source.list_count == 1  # cached, not re-listed


@pytest.mark.asyncio
async def test_only_two_meta_tools_are_bound_and_only_with_a_connection(
    db_session: AsyncSession,
) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    state = AgentState(project_id=project.id, messages=[HumanMessage("привет")])

    async def bound_names(provider: McpToolProvider | None) -> set[str]:
        chat_model = RecordingChatModel()
        await assistant(
            state,
            chat_model=chat_model,
            token_budget=100_000,
            project_store=SqliteProjectStore(db_session),
            usage_store=None,
            model_name="test-model",
            mcp_tools=provider,
        )
        return {tool.__name__ for tool in chat_model.bound_tools}

    names = await bound_names(None)
    assert META_TOOL_NAMES.isdisjoint(names)

    source = FakeMcpToolSource()
    names = await bound_names(McpToolProvider([_connection(source)]))
    assert META_TOOL_NAMES <= names
    # Progressive disclosure: the server's own tool is NOT bound directly, and
    # binding the meta-tools does not spawn/list the server.
    assert qualified_name("Dice Server", "roll-dice") not in names
    assert source.list_count == 0
