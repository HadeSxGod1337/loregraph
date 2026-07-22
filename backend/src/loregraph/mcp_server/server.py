"""Loregraph MCP server (stdio).

Lets external MCP clients (Claude Desktop etc.) read and carefully write the
local Loregraph database through the same service layer as the REST API and
the agent — validation rules can never diverge.

Write tools deliberately ask the client to confirm changes with the user
first. Do not enable auto-approve for them in your MCP client.

Nothing here can delete an entity or a project — losing one of those loses
text no other tool holds, so it stays in the web UI where it can be seen
before it happens. Removing a relationship is the one destructive operation
exposed. It destroys no content, only a typed link create_edge can put back;
denying it while allowing update_edge would be a pretense, since a client that
cannot unlink just re-types the link into something harmless. The in-app agent
can do the same under human review, and letting the two surfaces disagree is
its own hazard: a client with no way to unlink invents contradicting
duplicates instead.

Run: `loregraph-mcp` (configure CAMPAIGN_* env vars / .env as for the app).
"""

from typing import Any

from mcp.server.fastmcp import FastMCP

from loregraph.mcp_server.deps import edge_service, entity_service, get_session
from loregraph.schemas.edge import EdgeCreate, EdgeOut, EdgeUpdate
from loregraph.schemas.entity import (
    EntityCreate,
    EntityFieldIn,
    EntityOut,
    EntityUpdate,
    FieldType,
)
from loregraph.services.graph_query import get_subgraph
from loregraph.services.vector_index import entity_to_text
from loregraph.storage.sqlite.edge_store import SqliteEdgeStore
from loregraph.storage.sqlite.entity_store import SqliteEntityStore
from loregraph.storage.sqlite.project_store import SqliteProjectStore

mcp = FastMCP("loregraph")


def _entity_brief(entity: EntityOut) -> dict[str, Any]:
    return {"id": entity.id, "type": entity.type, "title": entity.title}


def _edge_brief(edge: EdgeOut) -> dict[str, Any]:
    """A relationship as clients see it — id included.

    Without the id a client can read the graph but never change it: both
    update_edge and delete_edge address a relationship by id, and this is the
    only place one is handed out."""
    return {
        "id": edge.id,
        "source": edge.source_entity_id,
        "target": edge.target_entity_id,
        "type": edge.type,
        "label": edge.label,
    }


@mcp.tool()
async def list_projects() -> list[dict[str, Any]]:
    """List all Loregraph projects (worlds/campaigns) with their ids."""
    async with await get_session() as session:
        projects = await SqliteProjectStore(session).list_projects()
        return [
            {"id": p.id, "name": p.name, "description": p.description} for p in projects
        ]


@mcp.tool()
async def list_entities(
    project_id: str, entity_type: str | None = None
) -> list[dict[str, Any]]:
    """List entities of a project (optionally filtered by type, e.g. 'npc',
    'faction', 'location'). Returns compact id/type/title records."""
    async with await get_session() as session:
        entities = await SqliteEntityStore(session).list_entities(
            project_id, entity_type=entity_type
        )
        return [_entity_brief(e) for e in entities]


@mcp.tool()
async def get_entity(project_id: str, entity_id: str) -> dict[str, Any]:
    """Get one entity with all its fields, as JSON."""
    async with await get_session() as session:
        service = entity_service(session)
        entity = await service.get_in_project(project_id, entity_id)
        return entity.model_dump(mode="json")


@mcp.tool()
async def search_entities(project_id: str, query: str) -> list[dict[str, Any]]:
    """Case-insensitive text search over entity titles and field text."""
    needle = query.casefold()
    async with await get_session() as session:
        entities = await SqliteEntityStore(session).list_entities(project_id)
        return [
            _entity_brief(e)
            for e in entities
            if needle in e.title.casefold() or needle in entity_to_text(e).casefold()
        ]


@mcp.tool()
async def get_entity_graph(
    project_id: str, entity_id: str, depth: int = 1
) -> dict[str, Any]:
    """Get the relationship neighborhood of an entity (BFS up to `depth`),
    with typed edges — who is connected to whom and how."""
    async with await get_session() as session:
        subgraph = await get_subgraph(
            SqliteEntityStore(session),
            SqliteEdgeStore(session),
            project_id,
            entity_id,
            depth=depth,
        )
        return {
            "nodes": [_entity_brief(n) for n in subgraph.nodes],
            "edges": [_edge_brief(e) for e in subgraph.edges],
        }


@mcp.tool()
async def list_edges(
    project_id: str, entity_id: str | None = None
) -> list[dict[str, Any]]:
    """List relationships in a project, or only those touching one entity.

    Each record carries the relationship's `id`, which update_edge and
    delete_edge need — get_entity_graph shows the same links but is meant for
    reading the shape of the graph."""
    async with await get_session() as session:
        edges = await edge_service(session).list_edges(project_id, entity_id)
        return [_edge_brief(e) for e in edges]


@mcp.tool()
async def create_entity(
    project_id: str,
    entity_type: str,
    title: str,
    fields: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create a new entity. WRITE TOOL: show the user exactly what will be
    created and get their confirmation BEFORE calling. `fields` is a mapping
    of field name to text value (e.g. {"role": "blacksmith"})."""
    field_models = [
        EntityFieldIn(key=key, field_type=FieldType.TEXT, value=value)
        for key, value in (fields or {}).items()
    ]
    async with await get_session() as session:
        service = entity_service(session)
        entity = await service.create(
            EntityCreate(type=entity_type, title=title, fields=field_models),
            project_id,
        )
        return entity.model_dump(mode="json")


@mcp.tool()
async def create_edge(
    project_id: str,
    source_entity_id: str,
    target_entity_id: str,
    edge_type: str,
    label: str | None = None,
) -> dict[str, Any]:
    """Create a typed relationship between two existing entities. WRITE TOOL:
    confirm with the user BEFORE calling. `edge_type` is short snake_case
    (ally_of, member_of, located_in, ...)."""
    async with await get_session() as session:
        edge = await edge_service(session).create(
            project_id,
            EdgeCreate(
                source_entity_id=source_entity_id,
                target_entity_id=target_entity_id,
                type=edge_type,
                label=label,
            ),
        )
        return edge.model_dump(mode="json")


@mcp.tool()
async def update_entity(
    project_id: str,
    entity_id: str,
    title: str | None = None,
    entity_type: str | None = None,
    fields: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Change an existing entity. WRITE TOOL: show the user the change and get
    their confirmation BEFORE calling. Call get_entity first — `fields`
    REPLACES the entity's fields rather than merging into them, so pass every
    field you want to keep. Omitted arguments leave that part unchanged."""
    async with await get_session() as session:
        service = entity_service(session)
        current = await service.get_in_project(project_id, entity_id)
        field_models = (
            [
                EntityFieldIn(key=key, field_type=FieldType.TEXT, value=value)
                for key, value in fields.items()
            ]
            if fields is not None
            else [
                EntityFieldIn(
                    key=field.key, field_type=field.field_type, value=field.value
                )
                for field in current.fields
            ]
        )
        entity = await service.update(
            project_id,
            entity_id,
            EntityUpdate(
                type=entity_type or current.type,
                title=title or current.title,
                fields=field_models,
            ),
        )
        return entity.model_dump(mode="json")


@mcp.tool()
async def update_edge(
    project_id: str,
    edge_id: str,
    edge_type: str | None = None,
    label: str | None = None,
    reverse: bool = False,
) -> dict[str, Any]:
    """Change an existing relationship: re-type it, relabel it, or flip its
    direction with `reverse`. WRITE TOOL: confirm with the user BEFORE
    calling. Get `edge_id` from list_edges. There is no way to move a
    relationship to a different entity — for that, delete_edge and create_edge
    a new one."""
    async with await get_session() as session:
        service = edge_service(session)
        current = await service.get_in_project(project_id, edge_id)
        edge = await service.update(
            project_id,
            edge_id,
            EdgeUpdate(
                type=edge_type or current.type,
                label=label if label is not None else current.label,
                reverse=reverse,
            ),
        )
        return edge.model_dump(mode="json")


@mcp.tool()
async def delete_edge(project_id: str, edge_id: str) -> dict[str, Any]:
    """Remove a relationship between two entities. WRITE TOOL, and the only
    destructive one here: confirm with the user BEFORE calling. The entities
    themselves are untouched — only the link between them goes. Get `edge_id`
    from list_edges."""
    async with await get_session() as session:
        service = edge_service(session)
        # Read first so the reply can say what was removed: a bare "ok" gives
        # the client nothing to show the user afterwards.
        edge = await service.get_in_project(project_id, edge_id)
        await service.delete(project_id, edge_id)
        return {"deleted": _edge_brief(edge)}


def main() -> None:
    mcp.run()  # stdio transport by default


if __name__ == "__main__":
    main()
