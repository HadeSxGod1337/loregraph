from typing import Annotated

from fastapi import APIRouter, Query

from loregraph.api.deps import EntityServiceDep
from loregraph.schemas.entity import (
    EntityCreate,
    EntityIconSet,
    EntityOut,
    EntityUpdate,
)

router = APIRouter(prefix="/projects/{project_id}/entities", tags=["entities"])


@router.get("", response_model=list[EntityOut])
async def list_entities(
    project_id: str,
    service: EntityServiceDep,
    entity_type: Annotated[str | None, Query(alias="type")] = None,
) -> list[EntityOut]:
    return await service.list_entities(project_id, entity_type=entity_type)


@router.post("", response_model=EntityOut, status_code=201)
async def create_entity(
    project_id: str, data: EntityCreate, service: EntityServiceDep
) -> EntityOut:
    return await service.create(data, project_id)


@router.get("/{entity_id}", response_model=EntityOut)
async def get_entity(
    project_id: str, entity_id: str, service: EntityServiceDep
) -> EntityOut:
    return await service.get_in_project(project_id, entity_id)


@router.put("/{entity_id}", response_model=EntityOut)
async def update_entity(
    project_id: str, entity_id: str, data: EntityUpdate, service: EntityServiceDep
) -> EntityOut:
    return await service.update(project_id, entity_id, data)


@router.delete("/{entity_id}", status_code=204)
async def delete_entity(
    project_id: str, entity_id: str, service: EntityServiceDep
) -> None:
    await service.delete(project_id, entity_id)


@router.put("/{entity_id}/icon", response_model=EntityOut)
async def set_entity_icon(
    project_id: str, entity_id: str, data: EntityIconSet, service: EntityServiceDep
) -> EntityOut:
    return await service.set_icon(project_id, entity_id, data.attachment_id)


@router.delete("/{entity_id}/icon", response_model=EntityOut)
async def clear_entity_icon(
    project_id: str, entity_id: str, service: EntityServiceDep
) -> EntityOut:
    return await service.set_icon(project_id, entity_id, None)
