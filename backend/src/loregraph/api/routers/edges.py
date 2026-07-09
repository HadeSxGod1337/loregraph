from typing import Annotated

from fastapi import APIRouter, Query

from loregraph.api.deps import EdgeStoreDep, EntityStoreDep
from loregraph.exceptions import InvalidEdgeReferenceError
from loregraph.schemas.edge import EdgeCreate, EdgeOut, EdgeUpdate

router = APIRouter(prefix="/edges", tags=["edges"])


@router.get("", response_model=list[EdgeOut])
async def list_edges(
    store: EdgeStoreDep,
    entity_id: Annotated[str | None, Query()] = None,
) -> list[EdgeOut]:
    if entity_id is None:
        return await store.list_all()
    return await store.list_for_entity(entity_id)


@router.post("", response_model=EdgeOut, status_code=201)
async def create_edge(
    data: EdgeCreate, edge_store: EdgeStoreDep, entity_store: EntityStoreDep
) -> EdgeOut:
    for entity_id in (data.source_entity_id, data.target_entity_id):
        if not await entity_store.exists(entity_id):
            raise InvalidEdgeReferenceError(entity_id)
    return await edge_store.create(data)


@router.put("/{edge_id}", response_model=EdgeOut)
async def update_edge(edge_id: str, data: EdgeUpdate, store: EdgeStoreDep) -> EdgeOut:
    return await store.update(edge_id, data)


@router.delete("/{edge_id}", status_code=204)
async def delete_edge(edge_id: str, store: EdgeStoreDep) -> None:
    await store.delete(edge_id)
