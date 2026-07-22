"""The manage_relationships pipeline: wiring entities that already exist.

The regression this suite exists for is narrow and was expensive — asked to
connect two existing characters, the agent used to invent a throwaway NPC to
hang the edge on, because a relationship's source was only ever allowed to be
an entity from the same draft. So every test here checks not just that the
right edge appeared, but that no entity did.
"""

from collections import deque
from collections.abc import AsyncGenerator
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
from loregraph.schemas.agent import DraftEntity, DraftRelationship, LoreDraft
from loregraph.schemas.edge import EdgeCreate
from loregraph.schemas.entity import EntityCreate, EntityOut
from loregraph.schemas.project import ProjectCreate
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

CONFIG: RunnableConfig = {"configurable": {"thread_id": "rel-t1"}}


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
    session: AsyncSession,
    script: list[AIMessage],
    extraction_results: list[BaseModel] | None = None,
    edge_service: EdgeService | None = None,
) -> Any:
    entity_store = SqliteEntityStore(session)
    edge_store = SqliteEdgeStore(session)
    return build_agent_graph(
        chat_model=ScriptedChatModel(script=deque(script)),
        creative=FakeGenerator([]),
        extraction=FakeGenerator(extraction_results or []),
        vector_index=None,
        knowledge_index=None,
        entity_store=entity_store,
        edge_store=edge_store,
        project_store=SqliteProjectStore(session),
        entity_service=EntityService(entity_store),
        edge_service=edge_service or EdgeService(edge_store, entity_store),
        token_budget=100_000,
        checkpointer=MemorySaver(),
    )


def manage_call(entity_ids: list[str], brief: str) -> AIMessage:
    return AIMessage(
        "",
        tool_calls=[
            {
                "name": "manage_relationships",
                "args": {"entity_ids": entity_ids, "brief": brief},
                "id": "mr1",
            }
        ],
    )


async def _world(session: AsyncSession) -> tuple[str, EntityOut, EntityOut]:
    """A project with Karina and Nikolai — the pair from the original bug."""
    project = await SqliteProjectStore(session).create(ProjectCreate(name="P"))
    store = SqliteEntityStore(session)
    karina = await store.create(
        EntityCreate(type="npc", title="Карина «Тень»", fields=[]), project.id
    )
    nikolai = await store.create(
        EntityCreate(type="npc", title="Николай «Тень»", fields=[]), project.id
    )
    return project.id, karina, nikolai


async def _run_to_review(graph: Any, project_id: str, prompt: str) -> None:
    await graph.ainvoke(
        {"project_id": project_id, "messages": [HumanMessage(prompt)]}, CONFIG
    )


async def agent_state(graph: Any) -> AgentState:
    return AgentState.model_validate((await graph.aget_state(CONFIG)).values)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


async def test_connecting_two_existing_entities_invents_nothing(
    db_session: AsyncSession,
) -> None:
    """The regression: a draft that only wires existing entities together.

    Before relationship ops existed this could not even be expressed, and the
    model compensated by inventing an entity to serve as the edge's source.
    """
    project_id, karina, nikolai = await _world(db_session)
    draft = LoreDraft(
        relationships=[
            DraftRelationship(
                source_ref=karina.id,
                target_ref=nikolai.id,
                type="family_of",
                reason="Карина — дочь Николая.",
            )
        ]
    )
    graph = make_graph(
        db_session,
        [manage_call([karina.id, nikolai.id], "свяжи Карину и Николая")],
        extraction_results=[draft],
    )
    await _run_to_review(graph, project_id, "свяжи Карину и Николая")

    snapshot = await graph.aget_state(CONFIG)
    assert any(task.interrupts for task in snapshot.tasks), "review gate must interrupt"
    state = await agent_state(graph)
    assert state.draft is not None
    assert state.draft.entities == []

    await graph.ainvoke(Command(resume={"action": "approve"}), CONFIG)

    edges = await SqliteEdgeStore(db_session).list_all(project_id)
    assert len(edges) == 1
    assert edges[0].source_entity_id == karina.id
    assert edges[0].target_entity_id == nikolai.id
    assert edges[0].type == "family_of"

    entities = await SqliteEntityStore(db_session).list_entities(project_id)
    assert [e.id for e in entities] == [karina.id, nikolai.id], (
        "wiring two entities together must not create a third"
    )


async def test_draft_entities_are_dropped_from_a_wiring_request(
    db_session: AsyncSession,
) -> None:
    """Even if the model slips an entity in, this pipeline refuses to write
    it — that slip is exactly the bug being fixed."""
    project_id, karina, nikolai = await _world(db_session)
    draft = LoreDraft(
        entities=[DraftEntity(ref="e1", type="npc", title="Мария", summary="...")],
        relationships=[
            DraftRelationship(
                source_ref=karina.id, target_ref=nikolai.id, type="family_of"
            )
        ],
    )
    graph = make_graph(
        db_session,
        [manage_call([karina.id, nikolai.id], "свяжи их")],
        extraction_results=[draft],
    )
    await _run_to_review(graph, project_id, "свяжи их")

    state = await agent_state(graph)
    assert state.draft is not None
    assert state.draft.entities == []
    assert any(w.code == "dropped_draft_entity" for w in state.warnings)


# ---------------------------------------------------------------------------
# update / delete
# ---------------------------------------------------------------------------


async def test_update_retypes_the_same_edge(db_session: AsyncSession) -> None:
    project_id, karina, nikolai = await _world(db_session)
    edge_store = SqliteEdgeStore(db_session)
    existing = await EdgeService(edge_store, SqliteEntityStore(db_session)).create(
        project_id,
        EdgeCreate(
            source_entity_id=karina.id, target_entity_id=nikolai.id, type="ally_of"
        ),
    )

    draft = LoreDraft(
        relationships=[
            DraftRelationship(
                op="update",
                edge_id=existing.id,
                type="enemy_of",
                reason="Поссорились.",
            )
        ]
    )
    graph = make_graph(
        db_session,
        [manage_call([karina.id, nikolai.id], "они теперь враги")],
        extraction_results=[draft],
    )
    await _run_to_review(graph, project_id, "они теперь враги")
    await graph.ainvoke(Command(resume={"action": "approve"}), CONFIG)

    edges = await edge_store.list_all(project_id)
    assert len(edges) == 1
    assert edges[0].id == existing.id, "an update must not replace the relationship"
    assert edges[0].type == "enemy_of"


async def test_update_without_a_type_keeps_the_current_one(
    db_session: AsyncSession,
) -> None:
    """A reverse-only op must not blank the type: EdgeUpdate replaces rather
    than patches, so the write path has to carry the current value over."""
    project_id, karina, nikolai = await _world(db_session)
    edge_store = SqliteEdgeStore(db_session)
    existing = await EdgeService(edge_store, SqliteEntityStore(db_session)).create(
        project_id,
        EdgeCreate(
            source_entity_id=karina.id,
            target_entity_id=nikolai.id,
            type="member_of",
            label="служит",
        ),
    )

    draft = LoreDraft(
        relationships=[
            DraftRelationship(op="update", edge_id=existing.id, reverse=True)
        ]
    )
    graph = make_graph(
        db_session,
        [manage_call([karina.id, nikolai.id], "разверни связь")],
        extraction_results=[draft],
    )
    await _run_to_review(graph, project_id, "разверни связь")
    await graph.ainvoke(Command(resume={"action": "approve"}), CONFIG)

    edges = await edge_store.list_all(project_id)
    assert edges[0].type == "member_of"
    assert edges[0].label == "служит"
    assert edges[0].source_entity_id == nikolai.id, "reverse must swap the endpoints"


async def test_delete_removes_the_edge_but_keeps_the_entities(
    db_session: AsyncSession,
) -> None:
    project_id, karina, nikolai = await _world(db_session)
    edge_store = SqliteEdgeStore(db_session)
    existing = await EdgeService(edge_store, SqliteEntityStore(db_session)).create(
        project_id,
        EdgeCreate(
            source_entity_id=karina.id, target_entity_id=nikolai.id, type="ally_of"
        ),
    )

    draft = LoreDraft(
        relationships=[DraftRelationship(op="delete", edge_id=existing.id)]
    )
    graph = make_graph(
        db_session,
        [manage_call([karina.id, nikolai.id], "убери связь")],
        extraction_results=[draft],
    )
    await _run_to_review(graph, project_id, "убери связь")
    await graph.ainvoke(Command(resume={"action": "approve"}), CONFIG)

    assert await edge_store.list_all(project_id) == []
    entities = await SqliteEntityStore(db_session).list_entities(project_id)
    assert len(entities) == 2, "removing a link must not touch the entities"


async def test_reject_leaves_the_graph_untouched(db_session: AsyncSession) -> None:
    project_id, karina, nikolai = await _world(db_session)
    edge_store = SqliteEdgeStore(db_session)
    existing = await EdgeService(edge_store, SqliteEntityStore(db_session)).create(
        project_id,
        EdgeCreate(
            source_entity_id=karina.id, target_entity_id=nikolai.id, type="ally_of"
        ),
    )

    draft = LoreDraft(
        relationships=[DraftRelationship(op="delete", edge_id=existing.id)]
    )
    graph = make_graph(
        db_session,
        [manage_call([karina.id, nikolai.id], "убери связь")],
        extraction_results=[draft],
    )
    await _run_to_review(graph, project_id, "убери связь")
    await graph.ainvoke(Command(resume={"action": "reject"}), CONFIG)

    assert len(await edge_store.list_all(project_id)) == 1


# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------


async def test_unknown_edge_id_is_dropped_not_fatal(db_session: AsyncSession) -> None:
    project_id, karina, nikolai = await _world(db_session)
    draft = LoreDraft(
        relationships=[DraftRelationship(op="delete", edge_id="edge_that_never_was")]
    )
    graph = make_graph(
        db_session,
        [manage_call([karina.id, nikolai.id], "убери связь")],
        extraction_results=[draft],
    )
    await _run_to_review(graph, project_id, "убери связь")

    state = await agent_state(graph)
    assert state.draft is not None
    assert state.draft.relationships == []
    assert any(w.code == "dropped_unknown_edge" for w in state.warnings)


async def test_self_relationship_is_dropped(db_session: AsyncSession) -> None:
    project_id, karina, nikolai = await _world(db_session)
    draft = LoreDraft(
        relationships=[
            DraftRelationship(source_ref=karina.id, target_ref=karina.id, type="knows")
        ]
    )
    graph = make_graph(
        db_session,
        [manage_call([karina.id, nikolai.id], "свяжи её с собой")],
        extraction_results=[draft],
    )
    await _run_to_review(graph, project_id, "свяжи её с собой")

    state = await agent_state(graph)
    assert state.draft is not None
    assert state.draft.relationships == []
    assert any(w.code == "dropped_self_relationship" for w in state.warnings)


async def test_scope_of_one_entity_stops_before_review(
    db_session: AsyncSession,
) -> None:
    project_id, karina, _ = await _world(db_session)
    graph = make_graph(
        db_session, [manage_call([karina.id], "свяжи её")], extraction_results=[]
    )
    await _run_to_review(graph, project_id, "свяжи её")

    snapshot = await graph.aget_state(CONFIG)
    assert not any(task.interrupts for task in snapshot.tasks), (
        "an empty scope must not trap the session at a review with nothing in it"
    )
    # commit's no-draft branch reports why, folding the warning codes into the
    # event it puts in the chat.
    state = await agent_state(graph)
    event = state.messages[-1].additional_kwargs["event"]
    assert event["code"] == "draft_failed"
    assert "relationship_scope_empty" in event["params"]["reason_codes"]


async def test_conflicting_type_warns_but_still_offers_the_op(
    db_session: AsyncSession,
) -> None:
    """A falling-out is a legitimate story beat — the DM decides, so this is a
    warning on the review card and not a rejection."""
    project_id, karina, nikolai = await _world(db_session)
    await EdgeService(
        SqliteEdgeStore(db_session), SqliteEntityStore(db_session)
    ).create(
        project_id,
        EdgeCreate(
            source_entity_id=karina.id, target_entity_id=nikolai.id, type="ally_of"
        ),
    )

    draft = LoreDraft(
        relationships=[
            DraftRelationship(
                source_ref=nikolai.id, target_ref=karina.id, type="enemy_of"
            )
        ]
    )
    graph = make_graph(
        db_session,
        [manage_call([karina.id, nikolai.id], "они рассорились")],
        extraction_results=[draft],
    )
    await _run_to_review(graph, project_id, "они рассорились")

    state = await agent_state(graph)
    assert state.draft is not None
    assert len(state.draft.relationships) == 1, "the op survives; the DM decides"
    conflict = next(w for w in state.warnings if w.code == "conflicting_relationship")
    assert conflict.params["existing_type"] == "ally_of"
    assert conflict.params["proposed_type"] == "enemy_of"


# ---------------------------------------------------------------------------
# ordering
# ---------------------------------------------------------------------------


async def test_delete_does_not_run_when_an_earlier_op_fails(
    db_session: AsyncSession,
) -> None:
    """Destructive last. A failed create must not leave the world with the
    edge it was meant to replace already gone — deletion is the one step no
    rollback can compensate, since a re-created edge gets a new id."""
    project_id, karina, nikolai = await _world(db_session)
    entity_store = SqliteEntityStore(db_session)
    edge_store = SqliteEdgeStore(db_session)
    real_service = EdgeService(edge_store, entity_store)
    doomed = await real_service.create(
        project_id,
        EdgeCreate(
            source_entity_id=karina.id, target_entity_id=nikolai.id, type="ally_of"
        ),
    )

    class ExplodingCreate(EdgeService):
        async def create(self, project_id: str, data: EdgeCreate) -> Any:
            raise RuntimeError("boom")

    draft = LoreDraft(
        relationships=[
            DraftRelationship(
                source_ref=karina.id, target_ref=nikolai.id, type="enemy_of"
            ),
            DraftRelationship(op="delete", edge_id=doomed.id),
        ]
    )
    graph = make_graph(
        db_session,
        [manage_call([karina.id, nikolai.id], "замени связь")],
        extraction_results=[draft],
        edge_service=ExplodingCreate(edge_store, entity_store),
    )
    await _run_to_review(graph, project_id, "замени связь")
    with pytest.raises(RuntimeError):
        await graph.ainvoke(Command(resume={"action": "approve"}), CONFIG)

    remaining = await edge_store.list_all(project_id)
    assert [e.id for e in remaining] == [doomed.id], (
        "the old relationship must survive a failed replacement"
    )
