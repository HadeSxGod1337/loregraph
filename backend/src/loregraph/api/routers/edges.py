from typing import Annotated

from fastapi import APIRouter, Query

from loregraph.api.deps import EdgeStoreDep, EntityStoreDep
from loregraph.exceptions import (
    CrossProjectEdgeError,
    EdgeNotFoundError,
    EntityNotFoundError,
    InvalidEdgeReferenceError,
)
from loregraph.schemas.edge import EdgeCreate, EdgeOut, EdgeUpdate
from loregraph.storage.protocols import EdgeStore

router = APIRouter(prefix="/projects/{project_id}/edges", tags=["edges"])


async def _get_in_project(store: EdgeStore, project_id: str, edge_id: str) -> EdgeOut:
    edge = await store.get(edge_id)
    if edge.project_id != project_id:
        raise EdgeNotFoundError(edge_id)
    return edge


@router.get("", response_model=list[EdgeOut])
async def list_edges(
    project_id: str,
    edge_store: EdgeStoreDep,
    entity_store: EntityStoreDep,
    entity_id: Annotated[str | None, Query()] = None,
) -> list[EdgeOut]:
    if entity_id is None:
        return await edge_store.list_all(project_id)
    entity = await entity_store.get(entity_id)
    if entity.project_id != project_id:
        raise EntityNotFoundError(entity_id)
    return await edge_store.list_for_entity(entity_id)


@router.post("", response_model=EdgeOut, status_code=201)
async def create_edge(
    project_id: str,
    data: EdgeCreate,
    edge_store: EdgeStoreDep,
    entity_store: EntityStoreDep,
) -> EdgeOut:
    for entity_id in (data.source_entity_id, data.target_entity_id):
        if not await entity_store.exists(entity_id):
            raise InvalidEdgeReferenceError(entity_id)
    source = await entity_store.get(data.source_entity_id)
    target = await entity_store.get(data.target_entity_id)
    if source.project_id != project_id or target.project_id != project_id:
        raise CrossProjectEdgeError(data.source_entity_id, data.target_entity_id)
    return await edge_store.create(data, project_id)


@router.put("/{edge_id}", response_model=EdgeOut)
async def update_edge(
    project_id: str, edge_id: str, data: EdgeUpdate, store: EdgeStoreDep
) -> EdgeOut:
    await _get_in_project(store, project_id, edge_id)
    return await store.update(edge_id, data)


@router.delete("/{edge_id}", status_code=204)
async def delete_edge(project_id: str, edge_id: str, store: EdgeStoreDep) -> None:
    await _get_in_project(store, project_id, edge_id)
    await store.delete(edge_id)
