from loregraph.exceptions import (
    CrossProjectEdgeError,
    EdgeNotFoundError,
    EntityNotFoundError,
    InvalidEdgeReferenceError,
)
from loregraph.schemas.edge import EdgeCreate, EdgeOut, EdgeUpdate
from loregraph.storage.protocols import EdgeStore, EntityStore


class EdgeService:
    """Single write path for edges.

    Owns the reference/cross-project validation so REST routers, MCP tools,
    and the agent's commit node all enforce identical rules.
    """

    def __init__(self, edge_store: EdgeStore, entity_store: EntityStore) -> None:
        self._edges = edge_store
        self._entities = entity_store

    async def list_edges(
        self, project_id: str, entity_id: str | None = None
    ) -> list[EdgeOut]:
        if entity_id is None:
            return await self._edges.list_all(project_id)
        entity = await self._entities.get(entity_id)
        if entity.project_id != project_id:
            raise EntityNotFoundError(entity_id)
        return await self._edges.list_for_entity(entity_id)

    async def get_in_project(self, project_id: str, edge_id: str) -> EdgeOut:
        edge = await self._edges.get(edge_id)
        if edge.project_id != project_id:
            raise EdgeNotFoundError(edge_id)
        return edge

    async def create(self, project_id: str, data: EdgeCreate) -> EdgeOut:
        for entity_id in (data.source_entity_id, data.target_entity_id):
            if not await self._entities.exists(entity_id):
                raise InvalidEdgeReferenceError(entity_id)
        source = await self._entities.get(data.source_entity_id)
        target = await self._entities.get(data.target_entity_id)
        if source.project_id != project_id or target.project_id != project_id:
            raise CrossProjectEdgeError(data.source_entity_id, data.target_entity_id)
        return await self._edges.create(data, project_id)

    async def update(self, project_id: str, edge_id: str, data: EdgeUpdate) -> EdgeOut:
        await self.get_in_project(project_id, edge_id)
        return await self._edges.update(edge_id, data)

    async def delete(self, project_id: str, edge_id: str) -> None:
        await self.get_in_project(project_id, edge_id)
        await self._edges.delete(edge_id)
