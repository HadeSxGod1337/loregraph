"""Loregraph MCP server (stdio).

Lets external MCP clients (Claude Desktop etc.) read and carefully write the
local Loregraph database through the same service layer as the REST API and
the agent — validation rules can never diverge.

Write tools deliberately ask the client to confirm changes with the user
first, and there are no delete tools: destructive operations stay in the web
UI. Do not enable auto-approve for the write tools in your MCP client.

Run: `loregraph-mcp` (configure CAMPAIGN_* env vars / .env as for the app).
"""

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from loregraph.config import Settings
from loregraph.schemas.edge import EdgeCreate
from loregraph.schemas.entity import EntityCreate, EntityFieldIn, EntityOut, FieldType
from loregraph.services.edge_service import EdgeService
from loregraph.services.entity_service import EntityService
from loregraph.services.graph_query import get_subgraph
from loregraph.services.vector_index import entity_to_text
from loregraph.storage.sqlite.db import (
    create_engine_for,
    init_db,
    make_session_factory,
)
from loregraph.storage.sqlite.edge_store import SqliteEdgeStore
from loregraph.storage.sqlite.entity_store import SqliteEntityStore
from loregraph.storage.sqlite.project_store import SqliteProjectStore

mcp = FastMCP("loregraph")

_settings = Settings()
_session_factory: async_sessionmaker[AsyncSession] | None = None
_init_lock = asyncio.Lock()


async def _get_session() -> AsyncSession:
    global _session_factory
    async with _init_lock:
        if _session_factory is None:
            engine = create_engine_for(_settings.db_path)
            await init_db(engine)
            _session_factory = make_session_factory(engine)
    return _session_factory()


def _entity_brief(entity: EntityOut) -> dict[str, Any]:
    return {"id": entity.id, "type": entity.type, "title": entity.title}


@mcp.tool()
async def list_projects() -> list[dict[str, Any]]:
    """List all Loregraph projects (worlds/campaigns) with their ids."""
    async with await _get_session() as session:
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
    async with await _get_session() as session:
        entities = await SqliteEntityStore(session).list_entities(
            project_id, entity_type=entity_type
        )
        return [_entity_brief(e) for e in entities]


@mcp.tool()
async def get_entity(project_id: str, entity_id: str) -> dict[str, Any]:
    """Get one entity with all its fields, as JSON."""
    async with await _get_session() as session:
        service = EntityService(SqliteEntityStore(session))
        entity = await service.get_in_project(project_id, entity_id)
        return entity.model_dump(mode="json")


@mcp.tool()
async def search_entities(project_id: str, query: str) -> list[dict[str, Any]]:
    """Case-insensitive text search over entity titles and field text."""
    needle = query.casefold()
    async with await _get_session() as session:
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
    async with await _get_session() as session:
        subgraph = await get_subgraph(
            SqliteEntityStore(session),
            SqliteEdgeStore(session),
            project_id,
            entity_id,
            depth=depth,
        )
        return {
            "nodes": [_entity_brief(n) for n in subgraph.nodes],
            "edges": [
                {
                    "source": e.source_entity_id,
                    "target": e.target_entity_id,
                    "type": e.type,
                    "label": e.label,
                }
                for e in subgraph.edges
            ],
        }


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
    async with await _get_session() as session:
        service = EntityService(SqliteEntityStore(session))
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
    async with await _get_session() as session:
        entity_store = SqliteEntityStore(session)
        service = EdgeService(SqliteEdgeStore(session), entity_store)
        edge = await service.create(
            project_id,
            EdgeCreate(
                source_entity_id=source_entity_id,
                target_entity_id=target_entity_id,
                type=edge_type,
                label=label,
            ),
        )
        return edge.model_dump(mode="json")


def main() -> None:
    mcp.run()  # stdio transport by default


if __name__ == "__main__":
    main()
