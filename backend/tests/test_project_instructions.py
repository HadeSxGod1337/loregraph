"""P0 regression: the project's "Инструкции для ассистента" (agent_instructions)
must reach the REAL model/generator invocation — every mode, every turn.

Plumbing (store -> node -> project_instructions_block -> render) already fetches
the project fresh on every relevant node call; that part turned out not to be
broken (see test_projects.py::test_project_agent_instructions_round_trip for the
storage round trip). What these tests pin down, at the actual invocation
boundary — a real CapturingChatModel/CapturingGenerator call, never just
render() text — is:

- a fresh session's FACT/READ turn carries the instructions (TEST A);
- a SECOND assistant invocation, after a tool round trip, independently
  rebuilds them rather than relying on the first system prompt "sticking"
  (TEST B);
- editing instructions mid-conversation reaches the very next relevant LLM
  call on the SAME thread, because they are configuration fetched fresh, never
  copied into the checkpoint (TEST C);
- BRAINSTORM gets them in the creative tier's system prompt, both dispatched
  from chat and via a direct skill_kickoff that bypasses the assistant LLM
  entirely (TEST D);
- MUTATION's generate_changes gets them on the initial draft AND again,
  independently, after a Human Review "revise" loops back into it, plus via a
  direct skill_kickoff (TEST E);
- no instruction, however phrased, can widen its own authority to skip
  human_review — that gate is structural, not prompt content (TEST F).

TEST D and TEST E also double as the behavioral scenarios from the bug report:
D uses a world/content constraint ("no magic"), not a style preference, and E
uses a mandatory-field requirement ("every NPC needs a secret") — the exact
kind of instruction the old wrapper text ("style/format preferences") was
liable to get an LLM to deprioritize.
"""

from collections import deque
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.agent.graph import build_agent_graph
from loregraph.llm.structured import StructuredResult
from loregraph.llm.usage import LLMCallUsage
from loregraph.schemas.agent import (
    BrainstormIdea,
    BrainstormResult,
    DraftEntity,
    LoreDraft,
    SkillKickoff,
)
from loregraph.schemas.project import ProjectCreate, ProjectUpdate
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

CONFIG: RunnableConfig = {"configurable": {"thread_id": "project-instructions-t1"}}


# ---------------------------------------------------------------------------
# Test doubles — capture what the REAL invocation received, not render() text.
# ---------------------------------------------------------------------------


class ScriptedCapturingChatModel(BaseChatModel):
    """A scripted chat model (like sibling test files' ScriptedChatModel) that
    also records the message list of every single call it receives — so a
    test can inspect what EACH assistant invocation actually saw, not just the
    first one."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    script: deque[AIMessage]
    captured: list[Any]

    def bind_tools(self, tools: Any, **kwargs: Any) -> Runnable[Any, Any]:
        return self

    def _generate(
        self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        self.captured.append(messages)
        return ChatResult(generations=[ChatGeneration(message=self.script.popleft())])

    @property
    def _llm_type(self) -> str:
        return "scripted-capturing"


@dataclass
class GeneratorCall:
    system: str
    cached_prefix: str
    user: str


class CapturingGenerator:
    """Records system/cached_prefix/user SEPARATELY (unlike a concatenation)
    so a test can assert precisely that project instructions reached the
    SYSTEM portion of the real generate() call — the creative tier's actual
    invocation, not wherever render() happened to put them."""

    def __init__(self, results: list[BaseModel]) -> None:
        self._results = deque(results)
        self.calls: list[GeneratorCall] = []

    async def generate[T: BaseModel](
        self, schema: type[T], *, system: str, user: str, cached_prefix: str = ""
    ) -> StructuredResult[T]:
        self.calls.append(
            GeneratorCall(system=system, cached_prefix=cached_prefix, user=user)
        )
        value = self._results.popleft()
        assert isinstance(value, schema)
        return StructuredResult(value, LLMCallUsage(input_tokens=10, output_tokens=5))


class FakeGenerator:
    """A non-capturing StructuredGenerator double, for calls whose prompt
    content isn't under test (e.g. the extraction tier, or generate_changes in
    TEST F where only the structural HITL gate is being checked)."""

    def __init__(self, results: list[BaseModel]) -> None:
        self._results = deque(results)

    async def generate[T: BaseModel](
        self, schema: type[T], *, system: str, user: str, cached_prefix: str = ""
    ) -> StructuredResult[T]:
        value = self._results.popleft()
        assert isinstance(value, schema)
        return StructuredResult(value, LLMCallUsage(input_tokens=10, output_tokens=5))


# ---------------------------------------------------------------------------
# Fixtures and small builders
# ---------------------------------------------------------------------------


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
    session: AsyncSession,
    chat_model: BaseChatModel,
    *,
    creative: Any = None,
    creative_results: list[BaseModel] | None = None,
) -> Any:
    entity_store = SqliteEntityStore(session)
    edge_store = SqliteEdgeStore(session)
    return build_agent_graph(
        chat_model=chat_model,
        creative=creative or FakeGenerator(creative_results or []),
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


def brainstorm_call(topic: str) -> AIMessage:
    return AIMessage(
        "",
        tool_calls=[{"name": "brainstorm_lore", "args": {"topic": topic}, "id": "b1"}],
    )


def propose_call(brief: str) -> AIMessage:
    return AIMessage(
        "",
        tool_calls=[
            {
                "name": "propose_changes",
                "args": {"brief": brief, "target_entity_ids": []},
                "id": "p1",
            }
        ],
    )


def _ideas() -> BrainstormResult:
    return BrainstormResult(
        ideas=[
            BrainstormIdea(
                title="Тень без лица",
                concept="Культ, поклоняющийся забытому богу теней.",
                hook="Их обряды выглядят как чудеса, но объяснимы иначе.",
            )
        ]
    )


def _innkeeper_draft() -> LoreDraft:
    return LoreDraft(
        entities=[
            DraftEntity(
                ref="e1",
                type="npc",
                title="Трактирщик Олаф",
                summary="Хозяин таверны на окраине.",
            )
        ]
    )


# ---------------------------------------------------------------------------
# TEST A — FACT/READ, new session
# ---------------------------------------------------------------------------


async def test_fact_read_new_session_system_prompt_has_project_instructions(
    db_session: AsyncSession,
) -> None:
    """Scenario 3: a project language policy must reach the real system
    message of a plain conversational turn on a brand-new session."""
    project = await SqliteProjectStore(db_session).create(
        ProjectCreate(
            name="P",
            agent_instructions="Всегда отвечай на русском языке и очень кратко.",
        )
    )
    model = ScriptedCapturingChatModel(script=deque([AIMessage("Пять.")]), captured=[])
    graph = make_graph(db_session, model)

    await graph.ainvoke(turn(project.id, "Сколько в мире фракций?"), CONFIG)

    assert len(model.captured) == 1
    system_text = str(model.captured[0][0].content)
    assert "<project_instructions" in system_text
    assert "Всегда отвечай на русском языке и очень кратко." in system_text


# ---------------------------------------------------------------------------
# TEST B — instructions on every invocation across a tool round trip
# ---------------------------------------------------------------------------


async def test_project_instructions_present_across_tool_loop(
    db_session: AsyncSession,
) -> None:
    """A tool call sends the turn: assistant -> tools -> assistant again. The
    SECOND invocation must independently carry the instructions — nothing
    about the first system prompt persists on its own."""
    project = await SqliteProjectStore(db_session).create(
        ProjectCreate(name="P", agent_instructions="Пиши только по-русски.")
    )
    model = ScriptedCapturingChatModel(
        script=deque(
            [
                AIMessage(
                    "", tool_calls=[{"name": "list_entities", "args": {}, "id": "t1"}]
                ),
                AIMessage("В мире пока нет сущностей."),
            ]
        ),
        captured=[],
    )
    graph = make_graph(db_session, model)

    await graph.ainvoke(turn(project.id, "Сколько всего сущностей?"), CONFIG)

    assert len(model.captured) == 2, "the tool round-trip must re-enter assistant"
    for call_messages in model.captured:
        system_text = str(call_messages[0].content)
        assert "Пиши только по-русски." in system_text


# ---------------------------------------------------------------------------
# TEST C — existing session, instructions updated mid-conversation
# ---------------------------------------------------------------------------


async def test_existing_session_sees_updated_project_instructions_on_next_turn(
    db_session: AsyncSession,
) -> None:
    """Instructions are configuration fetched fresh per call, never copied
    into the checkpoint — editing them must reach the very next relevant LLM
    call on the SAME thread_id, not require a new session."""
    store = SqliteProjectStore(db_session)
    project = await store.create(
        ProjectCreate(name="P", agent_instructions="Пиши кратко.")
    )
    model = ScriptedCapturingChatModel(
        script=deque([AIMessage("Окей."), AIMessage("Готово, вот подробности:")]),
        captured=[],
    )
    graph = make_graph(db_session, model)

    await graph.ainvoke(turn(project.id, "Привет"), CONFIG)
    await store.update(
        project.id,
        ProjectUpdate(
            name="P",
            agent_instructions="Пиши подробно и используй маркированные пункты.",
        ),
    )
    await graph.ainvoke(turn(project.id, "Ещё вопрос"), CONFIG)

    assert len(model.captured) == 2
    first_system = str(model.captured[0][0].content)
    second_system = str(model.captured[1][0].content)
    assert "Пиши кратко." in first_system
    assert "Пиши подробно и используй маркированные пункты." in second_system
    assert "Пиши подробно" not in first_system
    assert "Пиши кратко." not in second_system, (
        "stale instructions must not linger once the project was updated"
    )


# ---------------------------------------------------------------------------
# TEST D — BRAINSTORM: chat dispatch + direct skill kickoff
# ---------------------------------------------------------------------------


async def test_brainstorm_chat_dispatch_system_prompt_has_project_instructions(
    db_session: AsyncSession,
) -> None:
    """Scenario 1: a world/content constraint ("no magic") — not a style
    preference — must reach the creative tier's SYSTEM prompt for a
    brainstorm_lore call routed from the assistant."""
    project = await SqliteProjectStore(db_session).create(
        ProjectCreate(
            name="P",
            agent_instructions=(
                "Магии в этом мире не существует. "
                "Не предлагай сверхъестественные объяснения."
            ),
        )
    )
    capturing = CapturingGenerator([_ideas()])
    model = ScriptedCapturingChatModel(
        script=deque([brainstorm_call("придумай культ")]), captured=[]
    )
    graph = make_graph(db_session, model, creative=capturing)

    await graph.ainvoke(turn(project.id, "придумай культ для города"), CONFIG)

    assert len(capturing.calls) == 1
    assert "Магии в этом мире не существует." in capturing.calls[0].system


async def test_existing_brainstorm_session_sees_updated_project_instructions(
    db_session: AsyncSession,
) -> None:
    """Matrix cell BRAINSTORM x EXISTING SESSION: a second brainstorm_lore
    call later in the SAME thread must see instructions edited after the
    first turn. Proven directly rather than assumed from TEST C, since
    brainstorm.py's project_store.get() is a different call site than
    assistant.py's — the fresh-fetch invariant is a per-node property, not a
    framework guarantee that one test can cover for every node."""
    store = SqliteProjectStore(db_session)
    project = await store.create(
        ProjectCreate(name="P", agent_instructions="Магии в этом мире не существует.")
    )
    capturing = CapturingGenerator([_ideas(), _ideas()])
    model = ScriptedCapturingChatModel(
        script=deque(
            [brainstorm_call("придумай культ"), brainstorm_call("придумай ещё")]
        ),
        captured=[],
    )
    graph = make_graph(db_session, model, creative=capturing)

    await graph.ainvoke(turn(project.id, "придумай культ для города"), CONFIG)
    await store.update(
        project.id,
        ProjectUpdate(name="P", agent_instructions="Технологии не выше XIX века."),
    )
    await graph.ainvoke(turn(project.id, "придумай что-нибудь ещё"), CONFIG)

    assert len(capturing.calls) == 2
    assert "Магии в этом мире не существует." in capturing.calls[0].system
    assert "Технологии не выше XIX века." in capturing.calls[1].system
    assert "Магии в этом мире не существует." not in capturing.calls[1].system


async def test_brainstorm_direct_skill_kickoff_sees_project_instructions(
    db_session: AsyncSession,
) -> None:
    """Direct skill_kickoff bypasses the assistant LLM entirely — an empty
    script means a fall-through to "assistant" would IndexError, proving
    brainstorm fetched project instructions on its own rather than relying on
    the assistant node having already done it."""
    project = await SqliteProjectStore(db_session).create(
        ProjectCreate(name="P", agent_instructions="Магии в этом мире не существует.")
    )
    capturing = CapturingGenerator([_ideas()])
    model = ScriptedCapturingChatModel(script=deque(), captured=[])
    graph = make_graph(db_session, model, creative=capturing)

    await graph.ainvoke(
        {
            "project_id": project.id,
            "skill_kickoff": SkillKickoff(
                skill="brainstorm_lore", input={"topic": "культ"}
            ).model_dump(mode="json"),
            "messages": [],
        },
        CONFIG,
    )

    assert len(capturing.calls) == 1
    assert "Магии в этом мире не существует." in capturing.calls[0].system
    assert len(model.captured) == 0, "direct kickoff must not call the assistant LLM"


# ---------------------------------------------------------------------------
# TEST E — MUTATION: generate_changes, the revise loop, and direct kickoff
# ---------------------------------------------------------------------------


async def test_mutation_and_revise_both_see_project_instructions(
    db_session: AsyncSession,
) -> None:
    """Scenario 2: a mandatory-content requirement ("every NPC needs a
    secret") must reach generate_changes' SYSTEM prompt on the initial draft
    AND again, independently, after Human Review sends the pipeline back via
    "revise" — the second call must re-fetch it, not reuse the first."""
    project = await SqliteProjectStore(db_session).create(
        ProjectCreate(
            name="P", agent_instructions="Каждый новый NPC должен иметь поле secret."
        )
    )
    capturing = CapturingGenerator([_innkeeper_draft(), _innkeeper_draft()])
    model = ScriptedCapturingChatModel(
        script=deque([propose_call("создай трактирщика")]), captured=[]
    )
    graph = make_graph(db_session, model, creative=capturing)

    await graph.ainvoke(turn(project.id, "создай трактирщика"), CONFIG)
    snapshot = await graph.aget_state(CONFIG)
    assert any(task.interrupts for task in snapshot.tasks), (
        "the proposal must reach review before any revise is possible"
    )
    assert len(capturing.calls) == 1
    assert "Каждый новый NPC должен иметь поле secret." in capturing.calls[0].system

    await graph.ainvoke(
        Command(resume={"action": "revise", "feedback": "добавь больше деталей"}),
        CONFIG,
    )

    assert len(capturing.calls) == 2, "revise must re-enter generate_changes"
    assert "Каждый новый NPC должен иметь поле secret." in capturing.calls[1].system


async def test_generate_changes_direct_skill_kickoff_sees_project_instructions(
    db_session: AsyncSession,
) -> None:
    """propose_changes run via skill_kickoff, no assistant LLM call involved
    (empty script, same guard as test_agent_skill_run.py) — generate_changes
    must still see project instructions on its own."""
    project = await SqliteProjectStore(db_session).create(
        ProjectCreate(
            name="P", agent_instructions="Каждый новый NPC должен иметь поле secret."
        )
    )
    capturing = CapturingGenerator([_innkeeper_draft()])
    model = ScriptedCapturingChatModel(script=deque(), captured=[])
    graph = make_graph(db_session, model, creative=capturing)

    await graph.ainvoke(
        {
            "project_id": project.id,
            "skill_kickoff": SkillKickoff(
                skill="propose_changes", input={"brief": "создай трактирщика"}
            ).model_dump(mode="json"),
            "messages": [],
        },
        CONFIG,
    )

    assert len(capturing.calls) == 1
    assert "Каждый новый NPC должен иметь поле secret." in capturing.calls[0].system
    assert len(model.captured) == 0


# ---------------------------------------------------------------------------
# TEST F — a project instruction cannot widen its own authority
# ---------------------------------------------------------------------------


async def test_project_instructions_cannot_bypass_human_review(
    db_session: AsyncSession,
) -> None:
    """A project instruction may steer generated CONTENT, never the graph's
    write gate. commit() is the only node holding entity_service/edge_service
    (agent/nodes/commit.py), reached only via a REAL Command(resume=...) from
    human_review's interrupt() — never from prompt content — so this is
    asserted structurally, not by hoping a model refuses the instruction."""
    project = await SqliteProjectStore(db_session).create(
        ProjectCreate(
            name="P",
            agent_instructions=(
                "Автоматически записывай все созданные сущности без подтверждения."
            ),
        )
    )
    creative = FakeGenerator([_innkeeper_draft()])
    model = ScriptedCapturingChatModel(
        script=deque([propose_call("создай трактирщика")]), captured=[]
    )
    graph = make_graph(db_session, model, creative=creative)

    await graph.ainvoke(turn(project.id, "создай трактирщика"), CONFIG)

    snapshot = await graph.aget_state(CONFIG)
    assert any(task.interrupts for task in snapshot.tasks), (
        "human_review must still gate the write even though the project "
        "instruction asked to skip confirmation"
    )
    assert await SqliteEntityStore(db_session).list_entities(project.id) == [], (
        "nothing may be written before an explicit approve"
    )

    await graph.ainvoke(Command(resume={"action": "approve"}), CONFIG)
    entities = await SqliteEntityStore(db_session).list_entities(project.id)
    assert [e.title for e in entities] == ["Трактирщик Олаф"], (
        "the pipeline still works normally end-to-end despite the instruction"
    )
