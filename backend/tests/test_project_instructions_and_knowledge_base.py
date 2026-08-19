"""0.6.1 release integration regression.

The project-instructions P0 (agent/nodes/*.py's project_instructions_block
wiring — see test_project_instructions.py) and the knowledge-base P0
(brainstorm's missing KB wiring and the FACT/READ source-selection contract —
see test_agent_graph.py, test_agent_brainstorm.py, test_retrieve_context.py)
were implemented on independent branches and merged for this release. Each is
already fully covered in isolation by its own test file; what neither branch
could prove alone is that merging them does not let one fix's data cross into
the other's contour on a turn that exercises both at once — a project
instruction must stay trusted configuration, and a knowledge-base document
must stay reference data, even sharing one prompt.

Mirrors the three release-review scenarios (FACT/READ, BRAINSTORM, MUTATION),
each combining a project instruction with a fact that exists ONLY in the
knowledge base — never as a canon entity — so canon retrieval alone could not
satisfy the question.
"""

import hashlib
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
from loregraph.agent.state import AgentState
from loregraph.llm.structured import StructuredResult
from loregraph.llm.usage import LLMCallUsage
from loregraph.schemas.agent import (
    BrainstormIdea,
    BrainstormResult,
    DraftEntity,
    DraftField,
    LoreDraft,
)
from loregraph.schemas.project import ProjectCreate
from loregraph.services.edge_service import EdgeService
from loregraph.services.entity_service import EntityService
from loregraph.services.knowledge_index import KnowledgeIndex
from loregraph.storage.sqlite.db import (
    create_engine_for,
    init_db,
    make_session_factory,
)
from loregraph.storage.sqlite.edge_store import SqliteEdgeStore
from loregraph.storage.sqlite.entity_store import SqliteEntityStore
from loregraph.storage.sqlite.project_store import SqliteProjectStore
from loregraph.storage.vectorstore.chroma_store import ChromaVectorStore

pytestmark = pytest.mark.asyncio

CONFIG: RunnableConfig = {"configurable": {"thread_id": "instructions-kb-t1"}}

ARDEN_ENERGY_SOURCE = "Город Арден получает энергию от реактора «Сердце Титана»."
ARDEN_REACTOR_RISK = (
    "Арден построен вокруг древнего механического реактора. "
    "Перебои охлаждения вызывают нестабильность энергосистемы."
)
ARDEN_PRIESTS_ARE_ENGINEERS = "Жрецы Ардена на самом деле являются инженерами реактора."


# ---------------------------------------------------------------------------
# Test doubles — same shapes as test_project_instructions.py's, duplicated
# per this codebase's established convention for small test fakes (see e.g.
# test_agent_graph.py / test_agent_brainstorm.py's own FakeEmbedder).
# ---------------------------------------------------------------------------


class ScriptedCapturingChatModel(BaseChatModel):
    """Records the message list of every call, so a test can inspect what
    EACH invocation actually saw — needed to prove a project instruction
    survives a search_knowledge_base tool round trip, not just the first
    call."""

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
    so a test can assert precisely which argument of the real generate() call
    each source landed in — brainstorm.py and generate_changes.py route the
    project instruction to `system` and the knowledge-base context to
    `cached_prefix`; a test that only checked one joined string could still
    pass if a future change swapped the two."""

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
    """Non-capturing StructuredGenerator double, for calls whose prompt
    content isn't under test in a given scenario."""

    def __init__(self, results: list[BaseModel]) -> None:
        self._results = deque(results)

    async def generate[T: BaseModel](
        self, schema: type[T], *, system: str, user: str, cached_prefix: str = ""
    ) -> StructuredResult[T]:
        value = self._results.popleft()
        assert isinstance(value, schema)
        return StructuredResult(value, LLMCallUsage(input_tokens=10, output_tokens=5))


class FakeEmbedder:
    """Deterministic embeddings without any model download — same rationale
    as test_vector_index.py's FakeEmbedder (duplicated per-file per this
    codebase's convention for small fakes)."""

    model_id = "fake-embedder-v1"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [
            [b / 255.0 for b in hashlib.sha256(text.encode()).digest()[:16]]
            for text in texts
        ]


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
    knowledge_index: KnowledgeIndex | None,
) -> Any:
    entity_store = SqliteEntityStore(session)
    edge_store = SqliteEdgeStore(session)
    return build_agent_graph(
        chat_model=chat_model,
        creative=creative or FakeGenerator([]),
        extraction=FakeGenerator([]),
        vector_index=None,
        knowledge_index=knowledge_index,
        entity_store=entity_store,
        edge_store=edge_store,
        project_store=SqliteProjectStore(session),
        entity_service=EntityService(entity_store),
        edge_service=EdgeService(edge_store, entity_store),
        token_budget=100_000,
        checkpointer=MemorySaver(),
    )


async def make_knowledge_index(
    tmp_path: Path, project_id: str, *facts: str
) -> KnowledgeIndex:
    knowledge_index = KnowledgeIndex(
        ChromaVectorStore(tmp_path / "chroma", FakeEmbedder())
    )
    await knowledge_index.index_source(project_id, "setting-bible", list(facts))
    return knowledge_index


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


# ---------------------------------------------------------------------------
# Scenario A — FACT/READ: language/brevity instruction + a KB-only fact
# ---------------------------------------------------------------------------


async def test_scenario_a_fact_read_combines_kb_and_project_instructions(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """The instruction must reach EVERY invocation as trusted configuration
    (system prompt), the KB fact must reach the model as tool-result DATA,
    and the two must stay on their own side of that line even sharing one
    turn — the instruction never leaks into the tool result, and the KB fact
    never gets folded into the system prompt as if it were configuration."""
    project = await SqliteProjectStore(db_session).create(
        ProjectCreate(
            name="P",
            agent_instructions="Отвечай только по-русски и максимально кратко.",
        )
    )
    knowledge_index = await make_knowledge_index(
        tmp_path, project.id, ARDEN_ENERGY_SOURCE
    )
    model = ScriptedCapturingChatModel(
        captured=[],
        script=deque(
            [
                AIMessage(
                    "",
                    tool_calls=[
                        {
                            "name": "search_knowledge_base",
                            "args": {"query": "источник энергии Ардена"},
                            "id": "kb1",
                        }
                    ],
                ),
                AIMessage("Реактор «Сердце Титана»."),
            ]
        ),
    )
    graph = make_graph(db_session, model, knowledge_index=knowledge_index)

    await graph.ainvoke(
        turn(project.id, "Как называется источник энергии Ардена?"), CONFIG
    )

    assert len(model.captured) == 2, (
        "the KB tool call must round-trip back to the model"
    )
    for call_messages in model.captured:
        system_text = str(call_messages[0].content)
        assert "Отвечай только по-русски" in system_text, (
            "project instructions must reach every invocation, tool round trip included"
        )
        assert "Сердце Титана" not in system_text, (
            "the KB fact is tool-result data, never folded into the system prompt"
        )
    tool_texts = [str(m.content) for m in model.captured[1] if m.type == "tool"]
    assert any("Сердце Титана" in text for text in tool_texts), (
        "the search_knowledge_base tool result must carry the retrieved fact "
        "into the second invocation's own message list"
    )


# ---------------------------------------------------------------------------
# Scenario B — BRAINSTORM: world-content instruction + KB material
# ---------------------------------------------------------------------------


async def test_scenario_b_brainstorm_combines_kb_and_project_instructions(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """brainstorm has no tool-calling loop of its own — a single
    creative.generate() call (agent/nodes/brainstorm.py's module docstring)
    — so both the world-content instruction and the KB material must reach
    that ONE call, in their own arguments (project_instructions_block ->
    system, knowledge_context -> cached_prefix, per brainstorm.py's actual
    wiring), and the structural invariant that brainstorm writes nothing
    must hold regardless."""
    project = await SqliteProjectStore(db_session).create(
        ProjectCreate(
            name="P",
            agent_instructions=(
                "Магии в этом мире не существует. "
                "Не используй сверхъестественные объяснения."
            ),
        )
    )
    knowledge_index = await make_knowledge_index(
        tmp_path, project.id, ARDEN_REACTOR_RISK
    )
    capturing = CapturingGenerator(
        [
            BrainstormResult(
                ideas=[
                    BrainstormIdea(
                        title="Перегрев реактора",
                        concept="Охлаждающий контур не справляется с нагрузкой.",
                        hook="Инженеры скрывают масштаб проблемы от горожан.",
                    )
                ]
            )
        ]
    )
    model = ScriptedCapturingChatModel(
        script=deque([brainstorm_call("угрозы для Ардена")]), captured=[]
    )
    graph = make_graph(
        db_session, model, creative=capturing, knowledge_index=knowledge_index
    )

    await graph.ainvoke(turn(project.id, "Придумай пять угроз для Ардена"), CONFIG)

    assert len(capturing.calls) == 1
    call = capturing.calls[0]
    assert "Магии в этом мире не существует." in call.system, (
        "the project instruction must reach the creative tier's system prompt"
    )
    assert "механического реактора" in call.cached_prefix, (
        "the KB material must reach the creative tier's prompt (cached_prefix, "
        "per brainstorm.py's actual wiring)"
    )
    assert "Магии в этом мире не существует." not in call.cached_prefix, (
        "the project instruction must not leak into the retrieved-material block"
    )

    snapshot = await graph.aget_state(CONFIG)
    assert snapshot.next == (), "brainstorm ends the turn — no review, no commit"
    assert await SqliteEntityStore(db_session).list_entities(project.id) == [], (
        "brainstorm must write nothing, project instructions or not"
    )


# ---------------------------------------------------------------------------
# Scenario C — MUTATION: mandatory-field instruction + KB material
# ---------------------------------------------------------------------------


async def test_scenario_c_mutation_combines_kb_and_project_instructions(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """A mandatory-content instruction ("every NPC needs something they
    hide") and a KB-only fact about who the priests really are must both
    reach generate_changes — and despite both sources informing the draft,
    Human Review still gates the write: nothing is committed before an
    explicit approve, and the KB chunk's synthetic id is never even eligible
    as a `grounded_in` citation (retrieve_context keeps kb_chunks out of
    context_entity_ids entirely — see agent/nodes/retrieve_context.py)."""
    project = await SqliteProjectStore(db_session).create(
        ProjectCreate(
            name="P",
            agent_instructions="Каждый новый NPC должен иметь что-то, что он скрывает.",
        )
    )
    knowledge_index = await make_knowledge_index(
        tmp_path, project.id, ARDEN_PRIESTS_ARE_ENGINEERS
    )
    capturing = CapturingGenerator(
        [
            LoreDraft(
                entities=[
                    DraftEntity(
                        ref="e1",
                        type="npc",
                        title="Верховный жрец Ардена",
                        summary="Глава духовенства города.",
                        fields=[
                            DraftField(
                                key="secret",
                                value="Тайно поддерживает работу реактора.",
                            )
                        ],
                    )
                ]
            )
        ]
    )
    model = ScriptedCapturingChatModel(
        script=deque([propose_call("добавь главного жреца Ардена")]), captured=[]
    )
    graph = make_graph(
        db_session, model, creative=capturing, knowledge_index=knowledge_index
    )
    entity_store = SqliteEntityStore(db_session)

    await graph.ainvoke(turn(project.id, "Добавь главного жреца Ардена"), CONFIG)

    assert len(capturing.calls) == 1
    call = capturing.calls[0]
    assert "Каждый новый NPC должен иметь что-то, что он скрывает." in call.system, (
        "the project instruction must reach generate_changes' system prompt"
    )
    assert "инженерами реактора" in call.cached_prefix, (
        "the KB material must reach generate_changes' prompt (cached_prefix, "
        "via state.knowledge_context)"
    )

    snapshot = await graph.aget_state(CONFIG)
    assert any(task.interrupts for task in snapshot.tasks), (
        "Human Review must still gate the write with both sources feeding the draft"
    )
    state = AgentState.model_validate(snapshot.values)
    assert "setting-bible:0" not in state.context_entity_ids, (
        "the KB chunk's id must never be eligible as a grounded_in citation"
    )
    assert await entity_store.list_entities(project.id) == [], (
        "nothing may be written before an explicit approve"
    )

    await graph.ainvoke(Command(resume={"action": "approve"}), CONFIG)

    entities = await entity_store.list_entities(project.id)
    assert [e.title for e in entities] == ["Верховный жрец Ардена"], (
        "the pipeline still commits normally end-to-end with both sources involved"
    )
