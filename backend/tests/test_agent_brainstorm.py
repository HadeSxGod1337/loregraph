"""The creative, non-mutating brainstorm mode (agent/nodes/brainstorm.py).

The invariant these tests guard: a request for IDEAS ("придумай врага для
Ордена") produces options in chat and changes NOTHING — no review gate, no
commit, no entity or edge written. Suggesting an idea must never make it canon;
turning one into world content is a separate propose_changes the game master
asks for afterwards.
"""

import hashlib
from collections import deque
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, cast

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
from loregraph.agent.state import NO_KNOWLEDGE_SENTINEL, AgentState
from loregraph.llm.structured import StructuredResult
from loregraph.llm.usage import LLMCallUsage
from loregraph.schemas.agent import (
    BrainstormIdea,
    BrainstormResult,
    DraftEntity,
    LoreDraft,
)
from loregraph.schemas.entity import EntityCreate
from loregraph.schemas.project import ProjectCreate
from loregraph.services.edge_service import EdgeService
from loregraph.services.entity_service import EntityService
from loregraph.services.knowledge_index import KnowledgeIndex
from loregraph.services.vector_index import VectorIndex
from loregraph.storage.sqlite.db import (
    create_engine_for,
    init_db,
    make_session_factory,
)
from loregraph.storage.sqlite.edge_store import SqliteEdgeStore
from loregraph.storage.sqlite.entity_store import SqliteEntityStore
from loregraph.storage.sqlite.project_store import SqliteProjectStore
from loregraph.storage.vectorstore.chroma_store import ChromaVectorStore
from tests.fakes import FixedVectorIndex

pytestmark = pytest.mark.asyncio

CONFIG: RunnableConfig = {"configurable": {"thread_id": "brainstorm-t1"}}


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


class CapturingGenerator:
    """Records the prompts each generate() call was given, so a test can assert
    what canon the creative tier actually saw."""

    def __init__(self, results: list[BaseModel]) -> None:
        self._results = deque(results)
        self.prompts: list[str] = []

    async def generate[T: BaseModel](
        self, schema: type[T], *, system: str, user: str, cached_prefix: str = ""
    ) -> StructuredResult[T]:
        self.prompts.append(f"{system}\n{cached_prefix}\n{user}")
        value = self._results.popleft()
        assert isinstance(value, schema)
        return StructuredResult(value, LLMCallUsage(input_tokens=10, output_tokens=5))


class FakeEmbedder:
    """Deterministic embeddings without any model download — same rationale
    as test_vector_index.py's FakeEmbedder (duplicated per-file per this
    codebase's convention for small fakes)."""

    model_id = "fake-embedder-v1"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vectors.append([b / 255.0 for b in digest[:16]])
        return vectors


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
    script: list[AIMessage],
    *,
    creative: Any = None,
    creative_results: list[BaseModel] | None = None,
    extraction_results: list[BaseModel] | None = None,
    retrieved_entity_ids: list[str] | None = None,
    knowledge_index: KnowledgeIndex | None = None,
) -> Any:
    entity_store = SqliteEntityStore(session)
    edge_store = SqliteEdgeStore(session)
    return build_agent_graph(
        chat_model=ScriptedChatModel(script=deque(script)),
        creative=creative or FakeGenerator(creative_results or []),
        extraction=FakeGenerator(extraction_results or []),
        vector_index=(
            cast(VectorIndex, FixedVectorIndex(retrieved_entity_ids))
            if retrieved_entity_ids is not None
            else None
        ),
        knowledge_index=knowledge_index,
        entity_store=entity_store,
        edge_store=edge_store,
        project_store=SqliteProjectStore(session),
        entity_service=EntityService(entity_store),
        edge_service=EdgeService(edge_store, entity_store),
        token_budget=100_000,
        checkpointer=MemorySaver(),
    )


def brainstorm_call(
    topic: str,
    target_entity_ids: list[str] | None = None,
    count: int | None = None,
) -> AIMessage:
    args: dict[str, Any] = {"topic": topic}
    if target_entity_ids:
        args["target_entity_ids"] = target_entity_ids
    if count is not None:
        args["count"] = count
    return AIMessage(
        "", tool_calls=[{"name": "brainstorm_lore", "args": args, "id": "b1"}]
    )


def propose_call(brief: str, target_entity_ids: list[str] | None = None) -> AIMessage:
    return AIMessage(
        "",
        tool_calls=[
            {
                "name": "propose_changes",
                "args": {"brief": brief, "target_entity_ids": target_entity_ids or []},
                "id": "p1",
            }
        ],
    )


def turn(project_id: str, text: str) -> dict[str, Any]:
    return {"project_id": project_id, "messages": [HumanMessage(text)]}


async def state_of(graph: Any) -> AgentState:
    return AgentState.model_validate((await graph.aget_state(CONFIG)).values)


def _ideas() -> BrainstormResult:
    return BrainstormResult(
        ideas=[
            BrainstormIdea(
                title="Крыса-предатель",
                concept="Доверенный лейтенант Ордена тайно служит врагу.",
                hook="Разоблачение расколет Орден надвое.",
            ),
            BrainstormIdea(
                title="Зеркальный паладин",
                concept="Отрёкшийся рыцарь Ордена с теми же силами.",
                hook="Партия не сможет отличить его от союзника.",
            ),
        ],
        note="Какую идею развить?",
    )


async def test_brainstorm_answers_in_chat_and_writes_nothing(
    db_session: AsyncSession,
) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    graph = make_graph(
        db_session,
        [brainstorm_call("придумай врага для Ордена")],
        creative_results=[_ideas()],
    )

    await graph.ainvoke(turn(project.id, "придумай врага для Ордена"), CONFIG)

    snapshot = await graph.aget_state(CONFIG)
    assert not any(task.interrupts for task in snapshot.tasks), (
        "brainstorm must NOT open a review gate"
    )
    state = await state_of(graph)
    assert state.draft is None
    assert state.committed_entity_ids == []
    # The ideas are delivered as a normal assistant message.
    reply = str(state.messages[-1].content)
    assert "Крыса-предатель" in reply and "Зеркальный паладин" in reply
    # The world is untouched — nothing became canon.
    assert await SqliteEntityStore(db_session).list_entities(project.id) == []
    assert await SqliteEdgeStore(db_session).list_all(project.id) == []


async def test_brainstorm_grounds_ideas_in_the_target_entity(
    db_session: AsyncSession,
) -> None:
    """§use-existing-lore: the named target's canon reaches the creative tier,
    so an invented enemy plays against the real faction rather than floating
    free."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    order = await SqliteEntityStore(db_session).create(
        EntityCreate(type="faction", title="Орден Серебряного Пламени", fields=[]),
        project.id,
    )
    capturing = CapturingGenerator([_ideas()])
    graph = make_graph(
        db_session,
        [brainstorm_call("придумай врага", target_entity_ids=[order.id])],
        creative=capturing,
        retrieved_entity_ids=[order.id],
    )

    await graph.ainvoke(turn(project.id, "придумай врага для Ордена"), CONFIG)

    assert len(capturing.prompts) == 1
    assert "Орден Серебряного Пламени" in capturing.prompts[0]
    assert order.id in capturing.prompts[0]


async def test_brainstorm_then_add_becomes_a_reviewed_proposal(
    db_session: AsyncSession,
) -> None:
    """§options-then-choose: brainstorm writes nothing; a follow-up "add it"
    on the next turn is a normal reviewed proposal."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    chosen = LoreDraft(
        entities=[
            DraftEntity(
                ref="e1",
                type="npc",
                title="Крыса-предатель",
                summary="Лейтенант Ордена на службе врага.",
            )
        ]
    )
    graph = make_graph(
        db_session,
        [brainstorm_call("придумай пятерых врагов"), propose_call("добавь предателя")],
        creative_results=[_ideas(), chosen],
    )

    # Turn 1: brainstorm — no review, nothing written.
    await graph.ainvoke(turn(project.id, "придумай пятерых врагов"), CONFIG)
    assert not any(task.interrupts for task in (await graph.aget_state(CONFIG)).tasks)
    assert await SqliteEntityStore(db_session).list_entities(project.id) == []

    # Turn 2: "add the third" → a proposal that reaches review.
    await graph.ainvoke(turn(project.id, "беру третьего, добавь его"), CONFIG)
    snapshot = await graph.aget_state(CONFIG)
    assert any(task.interrupts for task in snapshot.tasks), "the add must reach review"
    state = await state_of(graph)
    assert state.draft is not None
    assert [e.title for e in state.draft.entities] == ["Крыса-предатель"]
    # Still nothing written until approval.
    assert await SqliteEntityStore(db_session).list_entities(project.id) == []

    # Approve → now it is canon.
    await graph.ainvoke(Command(resume={"action": "approve"}), CONFIG)
    entities = await SqliteEntityStore(db_session).list_entities(project.id)
    assert [e.title for e in entities] == ["Крыса-предатель"]


async def test_brainstorm_writes_nothing_even_with_a_reject_never_offered(
    db_session: AsyncSession,
) -> None:
    """There is no review to reject: the brainstorm turn ends at END, so the
    session is idle (not awaiting_review) right after it."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    graph = make_graph(
        db_session,
        [brainstorm_call("накидай идей")],
        creative_results=[_ideas()],
    )
    await graph.ainvoke(turn(project.id, "накидай идей"), CONFIG)
    snapshot = await graph.aget_state(CONFIG)
    assert snapshot.next == ()  # turn finished, not paused at an interrupt


async def test_brainstorm_receives_knowledge_base_context(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """P0 regression: graph.py never wired knowledge_index into the brainstorm
    node at all, so a creative prompt built on an uploaded setting document
    silently ignored it — brainstorm has no tool-calling loop of its own (a
    single creative.generate() call, not an agentic model), so this can only
    be fixed by retrieving the KB deterministically before generation, the
    same way canon is already gathered in _gather_material."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    knowledge_index = KnowledgeIndex(
        ChromaVectorStore(tmp_path / "chroma", FakeEmbedder())
    )
    await knowledge_index.index_source(
        project.id,
        "setting-bible",
        ["Город построен вокруг древнего механического реактора."],
    )
    capturing = CapturingGenerator([_ideas()])
    graph = make_graph(
        db_session,
        [brainstorm_call("какие проблемы могут возникнуть в этом городе")],
        creative=capturing,
        knowledge_index=knowledge_index,
    )

    await graph.ainvoke(
        turn(
            project.id,
            "придумай пять проблем, которые могут возникнуть в этом городе",
        ),
        CONFIG,
    )

    assert len(capturing.prompts) == 1
    assert "механического реактора" in capturing.prompts[0]


async def test_brainstorm_without_knowledge_index_uses_sentinel(
    db_session: AsyncSession,
) -> None:
    """Embeddings disabled (knowledge_index=None, the make_graph default):
    brainstorm must degrade cleanly, same NO_KNOWLEDGE_SENTINEL contract as
    retrieve_context, never a silent empty block the model reads as license
    to invent an upload that was never there."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    capturing = CapturingGenerator([_ideas()])
    graph = make_graph(
        db_session,
        [brainstorm_call("придумай проблему")],
        creative=capturing,
    )

    await graph.ainvoke(turn(project.id, "придумай проблему для города"), CONFIG)

    assert len(capturing.prompts) == 1
    assert NO_KNOWLEDGE_SENTINEL in capturing.prompts[0]
