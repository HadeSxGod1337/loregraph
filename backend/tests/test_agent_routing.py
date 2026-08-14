"""Turn routing: read-before-pipeline, mutation priority, and the tool loop
bound (agent/nodes/assistant.py).

These pin the ordering rules that keep the assistant honest when a single model
turn asks for several things at once — run the reads before a proposal that
needs their ids, let a mutation win over a bundled brainstorm, and stop a
runaway read-loop from burning the whole budget.
"""

from collections import deque
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.agent.graph import build_agent_graph
from loregraph.agent.nodes.assistant import (
    FORCE_ANSWER_DIRECTIVE,
    MAX_TOOL_ITERATIONS,
    _tool_iterations_this_turn,
    assistant,
)
from loregraph.agent.state import AgentState
from loregraph.llm.structured import StructuredResult
from loregraph.llm.usage import LLMCallUsage
from loregraph.schemas.agent import DraftEntity, LoreDraft
from loregraph.schemas.entity import EntityCreate
from loregraph.schemas.project import ProjectCreate, ProjectOut
from loregraph.services.edge_service import EdgeService
from loregraph.services.entity_service import EntityService
from loregraph.storage.sqlite.db import (
    create_engine_for,
    init_db,
    make_session_factory,
)
from loregraph.storage.sqlite.edge_store import SqliteEdgeStore
from loregraph.storage.sqlite.entity_store import SqliteEntityStore
from loregraph.storage.sqlite.project_store import SqliteProjectStore

pytestmark = pytest.mark.asyncio

CONFIG: RunnableConfig = {"configurable": {"thread_id": "routing-t1"}}


class ScriptedChatModel(BaseChatModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    script: deque[AIMessage]

    def bind_tools(self, tools: Any, **kwargs: Any) -> Runnable[Any, Any]:
        return self

    def _generate(
        self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self.script.popleft())])

    @property
    def _llm_type(self) -> str:
        return "scripted"


class FakeGenerator:
    def __init__(self, results: list[BaseModel]) -> None:
        self._results = deque(results)

    async def generate[T: BaseModel](
        self, schema: type[T], *, system: str, user: str, cached_prefix: str = ""
    ) -> StructuredResult[T]:
        value = self._results.popleft()
        assert isinstance(value, schema)
        return StructuredResult(value, LLMCallUsage(input_tokens=10, output_tokens=5))


@pytest_asyncio.fixture
async def db_session(tmp_path: Path) -> AsyncGenerator[AsyncSession, None]:
    engine = create_engine_for(tmp_path / "test.sqlite3")
    await init_db(engine)
    session = make_session_factory(engine)()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()


def make_graph(
    session: AsyncSession, script: list[AIMessage], creative_results: list[BaseModel]
) -> Any:
    entity_store = SqliteEntityStore(session)
    edge_store = SqliteEdgeStore(session)
    return build_agent_graph(
        chat_model=ScriptedChatModel(script=deque(script)),
        creative=FakeGenerator(creative_results),
        extraction=FakeGenerator([]),
        vector_index=None,
        knowledge_index=None,
        entity_store=entity_store,
        edge_store=edge_store,
        project_store=SqliteProjectStore(session),
        entity_service=EntityService(entity_store),
        edge_service=EdgeService(edge_store, entity_store),
        token_budget=100_000,
        checkpointer=MemorySaver(),
    )


def turn(project_id: str, text: str) -> dict[str, Any]:
    return {"project_id": project_id, "messages": [HumanMessage(text)]}


async def state_of(graph: Any) -> AgentState:
    return AgentState.model_validate((await graph.aget_state(CONFIG)).values)


def _tool_texts(state: AgentState) -> list[str]:
    return [str(m.content) for m in state.messages if m.type == "tool"]


def _new_npc_draft(title: str) -> LoreDraft:
    return LoreDraft(
        entities=[DraftEntity(ref="e1", type="npc", title=title, summary="—")]
    )


async def test_reads_run_before_a_bundled_proposal(db_session: AsyncSession) -> None:
    """§read-before-pipeline: a turn that emits a read AND propose_changes runs
    the read first and defers the proposal, so the model reissues it with the
    ids the read produced instead of starting on context it never received."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    await SqliteEntityStore(db_session).create(
        EntityCreate(type="npc", title="Мира Кузнец", fields=[]), project.id
    )
    mixed = AIMessage(
        "",
        tool_calls=[
            {"name": "search_lore", "args": {"query": "кузнец"}, "id": "s1"},
            {
                "name": "propose_changes",
                "args": {"brief": "создай нового кузнеца", "target_entity_ids": []},
                "id": "p1",
            },
        ],
    )
    graph = make_graph(
        db_session,
        [
            mixed,
            AIMessage(
                "",
                tool_calls=[
                    {
                        "name": "propose_changes",
                        "args": {
                            "brief": "создай нового кузнеца",
                            "target_entity_ids": [],
                        },
                        "id": "p2",
                    },
                ],
            ),
        ],
        [_new_npc_draft("Новый Кузнец")],
    )

    await graph.ainvoke(turn(project.id, "найди кузнеца и создай ещё одного"), CONFIG)

    snapshot = await graph.aget_state(CONFIG)
    assert any(task.interrupts for task in snapshot.tasks), (
        "the reissued proposal must reach review"
    )
    texts = _tool_texts(await state_of(graph))
    assert any("Мира" in t for t in texts), "the read must have actually run"
    assert any("was not started this turn" in t for t in texts), (
        "the bundled proposal must have been deferred, not started"
    )
    # Nothing written before approval — only the pre-existing entity is there.
    entities = await SqliteEntityStore(db_session).list_entities(project.id)
    assert {e.title for e in entities} == {"Мира Кузнец"}


async def test_mutation_wins_over_a_bundled_brainstorm(
    db_session: AsyncSession,
) -> None:
    """§creative+mutation: brainstorm_lore and propose_changes in one turn →
    the change is prepared for review, the brainstorm is deferred."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    both = AIMessage(
        "",
        tool_calls=[
            {"name": "brainstorm_lore", "args": {"topic": "враг"}, "id": "b1"},
            {
                "name": "propose_changes",
                "args": {"brief": "добавь врага", "target_entity_ids": []},
                "id": "p1",
            },
        ],
    )
    graph = make_graph(db_session, [both], [_new_npc_draft("Враг")])

    await graph.ainvoke(turn(project.id, "придумай врага и добавь его"), CONFIG)

    snapshot = await graph.aget_state(CONFIG)
    assert any(task.interrupts for task in snapshot.tasks), (
        "the proposal, not the brainstorm, must reach review"
    )
    state = await state_of(graph)
    assert state.draft is not None
    assert [e.title for e in state.draft.entities] == ["Враг"]
    assert any("only one proposal or brainstorm" in t for t in _tool_texts(state)), (
        "the brainstorm must have been deferred"
    )


# ---------------------------------------------------------------------------
# Tool loop bound
# ---------------------------------------------------------------------------


class _FakeProjectStore:
    async def get(self, project_id: str) -> ProjectOut:
        now = datetime(2026, 1, 1, tzinfo=UTC)
        return ProjectOut(
            id=project_id,
            name="P",
            description=None,
            agent_instructions=None,
            created_at=now,
            updated_at=now,
        )


class CapturingChatModel(BaseChatModel):
    """Records the messages it is invoked with, so a test can inspect the system
    prompt the assistant node assembled."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    captured: list[Any]

    def bind_tools(self, tools: Any, **kwargs: Any) -> Runnable[Any, Any]:
        return self

    def _generate(
        self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        self.captured.append(messages)
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage("final answer"))]
        )

    @property
    def _llm_type(self) -> str:
        return "capturing"


def _turn_history(tool_turns: int) -> list[Any]:
    messages: list[Any] = [HumanMessage("вопрос")]
    for index in range(tool_turns):
        messages.append(
            AIMessage(
                "", tool_calls=[{"name": "search_lore", "args": {}, "id": f"s{index}"}]
            )
        )
        messages.append(ToolMessage("result", tool_call_id=f"s{index}"))
    return messages


async def test_tool_iterations_counts_only_the_current_turn() -> None:
    messages: list[Any] = [
        HumanMessage("a"),
        AIMessage("", tool_calls=[{"name": "search_lore", "args": {}, "id": "1"}]),
        ToolMessage("r", tool_call_id="1"),
        HumanMessage("b"),  # a new user turn resets the count
        AIMessage("", tool_calls=[{"name": "search_lore", "args": {}, "id": "2"}]),
        ToolMessage("r", tool_call_id="2"),
    ]
    assert _tool_iterations_this_turn(messages) == 1


async def test_loop_bound_directs_an_answer_at_the_ceiling() -> None:
    model = CapturingChatModel(captured=[])
    state = AgentState(project_id="p", messages=_turn_history(MAX_TOOL_ITERATIONS))
    await assistant(
        state,
        chat_model=model,
        token_budget=100_000,
        project_store=_FakeProjectStore(),  # type: ignore[arg-type]
        usage_store=None,
        model_name="m",
    )
    system_text = str(model.captured[0][0].content)
    assert FORCE_ANSWER_DIRECTIVE.strip() in system_text


async def test_loop_below_ceiling_leaves_tools_available() -> None:
    model = CapturingChatModel(captured=[])
    state = AgentState(project_id="p", messages=_turn_history(MAX_TOOL_ITERATIONS - 1))
    await assistant(
        state,
        chat_model=model,
        token_budget=100_000,
        project_store=_FakeProjectStore(),  # type: ignore[arg-type]
        usage_store=None,
        model_name="m",
    )
    system_text = str(model.captured[0][0].content)
    assert FORCE_ANSWER_DIRECTIVE.strip() not in system_text
