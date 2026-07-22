"""The stdio MCP server's tools.

Previously untestable: the module read the environment at import time, so
nothing could load it without a configured database. With the composition root
in mcp_server/deps.py, the session factory can be pointed at a temp file and
the tools exercised directly.

What matters here is that every tool goes through the shared services, so the
rules an MCP client meets are the same ones the REST API and the agent's
commit node enforce — cross-project isolation above all.
"""

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio

from loregraph.exceptions import CrossProjectEdgeError, EdgeNotFoundError
from loregraph.mcp_server import deps, server
from loregraph.schemas.entity import EntityCreate
from loregraph.schemas.project import ProjectCreate
from loregraph.storage.sqlite.db import (
    create_engine_for,
    init_db,
    make_session_factory,
)
from loregraph.storage.sqlite.entity_store import SqliteEntityStore
from loregraph.storage.sqlite.project_store import SqliteProjectStore

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def mcp_db(tmp_path: Path) -> AsyncGenerator[None, None]:
    """Point the server's module-level session factory at a temp database."""
    engine = create_engine_for(tmp_path / "mcp.sqlite3")
    await init_db(engine)
    deps._session_factory = make_session_factory(engine)
    deps._vector_index = None
    try:
        yield
    finally:
        deps._session_factory = None
        await engine.dispose()


async def _project(name: str = "P") -> str:
    async with await deps.get_session() as session:
        project = await SqliteProjectStore(session).create(ProjectCreate(name=name))
        return project.id


async def _entity(project_id: str, title: str) -> str:
    async with await deps.get_session() as session:
        entity = await SqliteEntityStore(session).create(
            EntityCreate(type="npc", title=title, fields=[]), project_id
        )
        return entity.id


# ---------------------------------------------------------------------------
# Reading the graph
# ---------------------------------------------------------------------------


async def test_list_edges_exposes_the_id(mcp_db: None) -> None:
    """The id is the whole point: without it a client can read the graph but
    never change it, since update_edge and delete_edge address an edge by id.
    """
    project_id = await _project()
    a, b = await _entity(project_id, "A"), await _entity(project_id, "B")
    created = await server.create_edge(project_id, a, b, "ally_of")

    edges = await server.list_edges(project_id)
    assert [e["id"] for e in edges] == [created["id"]]
    assert edges[0]["source"] == a
    assert edges[0]["type"] == "ally_of"


async def test_list_edges_filters_by_entity(mcp_db: None) -> None:
    project_id = await _project()
    a, b, c = (
        await _entity(project_id, "A"),
        await _entity(project_id, "B"),
        await _entity(project_id, "C"),
    )
    await server.create_edge(project_id, a, b, "ally_of")
    await server.create_edge(project_id, b, c, "enemy_of")

    assert len(await server.list_edges(project_id, a)) == 1
    assert len(await server.list_edges(project_id, b)) == 2


async def test_entity_graph_carries_edge_ids(mcp_db: None) -> None:
    project_id = await _project()
    a, b = await _entity(project_id, "A"), await _entity(project_id, "B")
    created = await server.create_edge(project_id, a, b, "ally_of")

    graph = await server.get_entity_graph(project_id, a, depth=1)
    assert [e["id"] for e in graph["edges"]] == [created["id"]]


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


async def test_update_edge_retypes_in_place(mcp_db: None) -> None:
    project_id = await _project()
    a, b = await _entity(project_id, "A"), await _entity(project_id, "B")
    created = await server.create_edge(project_id, a, b, "ally_of", label="друзья")

    updated = await server.update_edge(project_id, created["id"], "enemy_of")
    assert updated["id"] == created["id"]
    assert updated["type"] == "enemy_of"
    assert updated["label"] == "друзья", "an omitted label must not be blanked"


async def test_update_edge_reverse_swaps_endpoints(mcp_db: None) -> None:
    project_id = await _project()
    a, b = await _entity(project_id, "A"), await _entity(project_id, "B")
    created = await server.create_edge(project_id, a, b, "member_of")

    updated = await server.update_edge(project_id, created["id"], reverse=True)
    assert updated["source_entity_id"] == b
    assert updated["type"] == "member_of", "reverse alone must keep the type"


async def test_delete_edge_reports_what_it_removed(mcp_db: None) -> None:
    project_id = await _project()
    a, b = await _entity(project_id, "A"), await _entity(project_id, "B")
    created = await server.create_edge(project_id, a, b, "ally_of")

    result = await server.delete_edge(project_id, created["id"])
    assert result["deleted"]["id"] == created["id"]
    assert await server.list_edges(project_id) == []
    # The entities are untouched — only the link between them went.
    assert len(await server.list_entities(project_id)) == 2


async def test_update_entity_keeps_untouched_parts(mcp_db: None) -> None:
    project_id = await _project()
    entity_id = await _entity(project_id, "Мира")

    updated = await server.update_entity(project_id, entity_id, title="Мира Кузнец")
    assert updated["title"] == "Мира Кузнец"
    assert updated["type"] == "npc", "an omitted type must not change"


# ---------------------------------------------------------------------------
# Shared-service guarantees
# ---------------------------------------------------------------------------


async def test_cross_project_edge_is_refused(mcp_db: None) -> None:
    """Inherited from EdgeService, not re-implemented here — that is the
    reason these tools go through the service layer at all."""
    project_a, project_b = await _project("A"), await _project("B")
    here, elsewhere = (
        await _entity(project_a, "Here"),
        await _entity(project_b, "Elsewhere"),
    )
    with pytest.raises(CrossProjectEdgeError):
        await server.create_edge(project_a, here, elsewhere, "ally_of")


async def test_deleting_another_projects_edge_is_refused(mcp_db: None) -> None:
    project_a, project_b = await _project("A"), await _project("B")
    a, b = await _entity(project_a, "A"), await _entity(project_a, "B")
    created = await server.create_edge(project_a, a, b, "ally_of")

    with pytest.raises(EdgeNotFoundError):
        await server.delete_edge(project_b, created["id"])
    assert len(await server.list_edges(project_a)) == 1
