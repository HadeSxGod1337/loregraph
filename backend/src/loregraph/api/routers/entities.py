from typing import Annotated

from fastapi import APIRouter, Query

from loregraph.api.deps import EntityStoreDep
from loregraph.exceptions import EntityNotFoundError
from loregraph.schemas.entity import (
    EntityCreate,
    EntityIconSet,
    EntityOut,
    EntityUpdate,
)
from loregraph.storage.protocols import EntityStore

router = APIRouter(prefix="/projects/{project_id}/entities", tags=["entities"])


async def _get_in_project(
    store: EntityStore, project_id: str, entity_id: str
) -> EntityOut:
    entity = await store.get(entity_id)
    if entity.project_id != project_id:
        # Wrong project for this id — 404, not 403: don't confirm the id
        # exists at all outside its own project.
        raise EntityNotFoundError(entity_id)
    return entity


@router.get("", response_model=list[EntityOut])
async def list_entities(
    project_id: str,
    store: EntityStoreDep,
    entity_type: Annotated[str | None, Query(alias="type")] = None,
) -> list[EntityOut]:
    return await store.list_entities(project_id, entity_type=entity_type)


@router.post("", response_model=EntityOut, status_code=201)
async def create_entity(
    project_id: str, data: EntityCreate, store: EntityStoreDep
) -> EntityOut:
    return await store.create(data, project_id)


@router.get("/{entity_id}", response_model=EntityOut)
async def get_entity(
    project_id: str, entity_id: str, store: EntityStoreDep
) -> EntityOut:
    return await _get_in_project(store, project_id, entity_id)


@router.put("/{entity_id}", response_model=EntityOut)
async def update_entity(
    project_id: str, entity_id: str, data: EntityUpdate, store: EntityStoreDep
) -> EntityOut:
    await _get_in_project(store, project_id, entity_id)
    return await store.update(entity_id, data)


@router.delete("/{entity_id}", status_code=204)
async def delete_entity(project_id: str, entity_id: str, store: EntityStoreDep) -> None:
    await _get_in_project(store, project_id, entity_id)
    await store.delete(entity_id)


@router.put("/{entity_id}/icon", response_model=EntityOut)
async def set_entity_icon(
    project_id: str, entity_id: str, data: EntityIconSet, store: EntityStoreDep
) -> EntityOut:
    await _get_in_project(store, project_id, entity_id)
    return await store.set_icon(entity_id, data.attachment_id)


@router.delete("/{entity_id}/icon", response_model=EntityOut)
async def clear_entity_icon(
    project_id: str, entity_id: str, store: EntityStoreDep
) -> EntityOut:
    await _get_in_project(store, project_id, entity_id)
    return await store.set_icon(entity_id, None)
