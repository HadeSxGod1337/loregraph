"""The agent side of the universal MCP passthrough: qualified naming,
building a chat-bindable schema from a tool's raw JSON Schema, dispatching a
chat tool call to the right connection, and conditional binding — all
against fake McpToolSources. Same invariant as the LiveSource tests: an
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
from pydantic import ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.agent.mcp_tools import (
    McpToolEntry,
    McpToolProvider,
    build_tool_model,
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
from loregraph.storage.sqlite.entity_store import SqliteEntityStore
from loregraph.storage.sqlite.project_store import SqliteProjectStore


class FakeMcpToolSource:
    def __init__(self, tools: list[RawMcpTool] | None = None) -> None:
        self.tools = tools or []
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def list_mcp_tools(self) -> list[RawMcpTool]:
        return self.tools

    async def call_mcp_tool(self, name: str, arguments: dict[str, Any]) -> str:
        self.calls.append((name, arguments))
        return f"called {name}"


class OfflineMcpToolSource:
    async def list_mcp_tools(self) -> list[RawMcpTool]:
        return []

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


def _entry(source: object, connection_name: str = "Dice Server") -> McpToolEntry:
    return McpToolEntry(
        connection_name=connection_name,
        connector_type="mcp",
        tool=_roll_dice_tool(),
        source=source,  # type: ignore[arg-type]
    )


def _tool_call_state(name: str, args: dict[str, Any]) -> AgentState:
    call = {"name": name, "args": args, "id": "call-1"}
    return AgentState(project_id="p1", messages=[AIMessage("", tool_calls=[call])])


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


def test_build_tool_model_reflects_required_and_optional_fields() -> None:
    entry = _entry(FakeMcpToolSource())

    model = build_tool_model(entry)

    assert model.__name__ == entry.qualified_name
    assert model.__doc__ == "Roll a die with the given number of sides."
    instance = model(sides=20)
    assert instance.sides == 20  # type: ignore[attr-defined]
    assert instance.label is None  # type: ignore[attr-defined]
    with pytest.raises(ValidationError):
        model()  # sides is required


@pytest.mark.asyncio
async def test_mcp_tool_call_dispatches_to_the_right_connection(
    db_session: AsyncSession,
) -> None:
    source = FakeMcpToolSource()
    provider = McpToolProvider([_entry(source)])
    name = qualified_name("Dice Server", "roll-dice")

    update = await run_tools(
        _tool_call_state(name, {"sides": 20}),
        vector_index=None,
        knowledge_index=None,
        entity_store=SqliteEntityStore(db_session),
        mcp_tools=provider,
    )

    content = update["messages"][0].content
    assert "called roll-dice" in content
    assert source.calls == [("roll-dice", {"sides": 20})]


@pytest.mark.asyncio
async def test_mcp_tool_call_offline_yields_message_not_exception(
    db_session: AsyncSession,
) -> None:
    provider = McpToolProvider([_entry(OfflineMcpToolSource())])
    name = qualified_name("Dice Server", "roll-dice")

    update = await run_tools(
        _tool_call_state(name, {"sides": 20}),
        vector_index=None,
        knowledge_index=None,
        entity_store=SqliteEntityStore(db_session),
        mcp_tools=provider,
    )

    content = update["messages"][0].content
    assert "unavailable" in content


@pytest.mark.asyncio
async def test_mcp_tool_call_unknown_name_degrades_gracefully(
    db_session: AsyncSession,
) -> None:
    update = await run_tools(
        _tool_call_state("mcp__Ghost__nope", {}),
        vector_index=None,
        knowledge_index=None,
        entity_store=SqliteEntityStore(db_session),
        mcp_tools=None,
    )

    content = update["messages"][0].content
    assert "No MCP tool sources are connected" in content


@pytest.mark.asyncio
async def test_mcp_tools_bound_only_when_a_connection_is_present(
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
    assert qualified_name("Dice Server", "roll-dice") not in names

    names = await bound_names(McpToolProvider([_entry(FakeMcpToolSource())]))
    assert qualified_name("Dice Server", "roll-dice") in names
