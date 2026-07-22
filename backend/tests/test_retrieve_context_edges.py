"""Existing relationships reaching the prompt, and reaching it addressably.

Two separate defects are pinned here. The edge lines used to carry no id, so
an existing relationship could be read but never named — nothing could edit or
remove one. And they were built from the anchor subgraph alone, so a run
without an anchor entity saw no relationships at all, which is precisely when
the model starts guessing at connections that already exist.
"""

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.agent.nodes.retrieve_context import MAX_CONTEXT_EDGES, retrieve_context
from loregraph.agent.state import AgentState
from loregraph.schemas.edge import EdgeCreate
from loregraph.schemas.entity import EntityCreate
from loregraph.schemas.project import ProjectCreate
from loregraph.services.edge_service import EdgeService
from loregraph.services.vector_index import VectorIndex
from loregraph.storage.sqlite.db import (
    create_engine_for,
    init_db,
    make_session_factory,
)
from loregraph.storage.sqlite.edge_store import SqliteEdgeStore
from loregraph.storage.sqlite.entity_store import SqliteEntityStore
from loregraph.storage.sqlite.project_store import SqliteProjectStore
from loregraph.storage.vectorstore.protocols import RetrievedChunk

pytestmark = pytest.mark.asyncio


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


class FakeVectorIndex:
    """Returns a fixed hit list — retrieval's entity scope comes from the
    vector tier, so seeding it is how a test says "these are the entities the
    model was shown"."""

    def __init__(self, entity_ids: list[str]) -> None:
        self._entity_ids = entity_ids

    async def query(
        self, project_id: str, text: str, k: int = 5
    ) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(entity_id=entity_id, text="", score=1.0)
            for entity_id in self._entity_ids[:k]
        ]


async def _retrieve(
    session: AsyncSession, state: AgentState, retrieved: list[str]
) -> dict[str, object]:
    return await retrieve_context(
        state,
        vector_index=cast(VectorIndex, FakeVectorIndex(retrieved)),
        knowledge_index=None,
        entity_store=SqliteEntityStore(session),
        edge_store=SqliteEdgeStore(session),
    )


async def test_existing_relationships_carry_their_id(
    db_session: AsyncSession,
) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    store = SqliteEntityStore(db_session)
    a = await store.create(
        EntityCreate(type="npc", title="Мира", fields=[]), project.id
    )
    b = await store.create(
        EntityCreate(type="faction", title="Гильдия", fields=[]), project.id
    )
    edge = await EdgeService(SqliteEdgeStore(db_session), store).create(
        project.id,
        EdgeCreate(source_entity_id=a.id, target_entity_id=b.id, type="member_of"),
    )

    # No anchor entity: this is the vector-only shape of retrieval, where the
    # anchor subgraph branch never runs.
    result = await _retrieve(
        db_session,
        AgentState(
            project_id=project.id,
            pending_brief="кто в гильдии",
        ),
        [a.id, b.id],
    )

    lore = str(result["existing_lore"])
    assert f'<relationship id="{edge.id}"' in lore, (
        "without the id an existing relationship cannot be updated or deleted"
    )
    assert "member_of" in lore
    assert "Мира" in lore and "Гильдия" in lore, "titles ride along, not bare ids"
    assert result["context_edge_ids"] == [edge.id]


async def test_relationships_appear_without_an_anchor_entity(
    db_session: AsyncSession,
) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    store = SqliteEntityStore(db_session)
    a = await store.create(EntityCreate(type="npc", title="A", fields=[]), project.id)
    b = await store.create(EntityCreate(type="npc", title="B", fields=[]), project.id)
    await EdgeService(SqliteEdgeStore(db_session), store).create(
        project.id,
        EdgeCreate(source_entity_id=a.id, target_entity_id=b.id, type="ally_of"),
    )

    state = AgentState(project_id=project.id, pending_brief="q")
    assert state.anchor_entity_id is None
    result = await _retrieve(db_session, state, [a.id, b.id])
    assert "ally_of" in str(result["existing_lore"])


async def test_edge_to_an_entity_outside_retrieval_is_not_shown(
    db_session: AsyncSession,
) -> None:
    """Both ends must be in scope: a relationship to something the model was
    never shown is context it cannot reason about or act on."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    store = SqliteEntityStore(db_session)
    a = await store.create(EntityCreate(type="npc", title="A", fields=[]), project.id)
    outsider = await store.create(
        EntityCreate(type="npc", title="Outsider", fields=[]), project.id
    )
    await EdgeService(SqliteEdgeStore(db_session), store).create(
        project.id,
        EdgeCreate(source_entity_id=a.id, target_entity_id=outsider.id, type="knows"),
    )

    result = await _retrieve(
        db_session,
        AgentState(project_id=project.id, pending_brief="q"),
        [a.id],
    )
    assert "knows" not in str(result["existing_lore"])
    assert result["context_edge_ids"] == []


async def test_truncation_is_stated_not_silent(db_session: AsyncSession) -> None:
    """A partial list the model reads as complete would make it conclude two
    entities are unconnected when they are."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    store = SqliteEntityStore(db_session)
    edge_service = EdgeService(SqliteEdgeStore(db_session), store)
    hub = await store.create(
        EntityCreate(type="location", title="Hub", fields=[]), project.id
    )
    spokes = [
        await store.create(
            EntityCreate(type="npc", title=f"NPC {i}", fields=[]), project.id
        )
        for i in range(MAX_CONTEXT_EDGES + 5)
    ]
    for spoke in spokes:
        await edge_service.create(
            project.id,
            EdgeCreate(
                source_entity_id=hub.id, target_entity_id=spoke.id, type="contains"
            ),
        )

    # Driven through the anchor subgraph rather than the vector tier, which
    # is capped at RETRIEVAL_K hits and could never put this many entities in
    # scope — a densely connected hub is how this limit is reached for real.
    result = await _retrieve(
        db_session,
        AgentState(project_id=project.id, pending_brief="q", anchor_entity_id=hub.id),
        [],
    )
    assert len(result["context_edge_ids"]) == MAX_CONTEXT_EDGES  # type: ignore[arg-type]
    assert "further relationships" in str(result["existing_lore"])
