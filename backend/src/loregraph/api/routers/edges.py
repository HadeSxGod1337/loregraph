from typing import Annotated

from fastapi import APIRouter, Query

from loregraph.api.deps import EdgeServiceDep
from loregraph.schemas.edge import EdgeCreate, EdgeOut, EdgeUpdate

router = APIRouter(prefix="/projects/{project_id}/edges", tags=["edges"])


@router.get("", response_model=list[EdgeOut])
async def list_edges(
    project_id: str,
    service: EdgeServiceDep,
    entity_id: Annotated[str | None, Query()] = None,
) -> list[EdgeOut]:
    return await service.list_edges(project_id, entity_id=entity_id)


@router.post("", response_model=EdgeOut, status_code=201)
async def create_edge(
    project_id: str, data: EdgeCreate, service: EdgeServiceDep
) -> EdgeOut:
    return await service.create(project_id, data)


@router.put("/{edge_id}", response_model=EdgeOut)
async def update_edge(
    project_id: str, edge_id: str, data: EdgeUpdate, service: EdgeServiceDep
) -> EdgeOut:
    return await service.update(project_id, edge_id, data)


@router.delete("/{edge_id}", status_code=204)
async def delete_edge(project_id: str, edge_id: str, service: EdgeServiceDep) -> None:
    await service.delete(project_id, edge_id)
