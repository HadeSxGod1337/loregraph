from typing import Annotated

from fastapi import APIRouter, Query

from loregraph.api.deps import EntityStoreDep
from loregraph.schemas.entity import (
    EntityCreate,
    EntityIconSet,
    EntityOut,
    EntityUpdate,
)

router = APIRouter(prefix="/entities", tags=["entities"])


@router.get("", response_model=list[EntityOut])
async def list_entities(
    store: EntityStoreDep,
    entity_type: Annotated[str | None, Query(alias="type")] = None,
) -> list[EntityOut]:
    return await store.list_entities(entity_type=entity_type)


@router.post("", response_model=EntityOut, status_code=201)
async def create_entity(data: EntityCreate, store: EntityStoreDep) -> EntityOut:
    return await store.create(data)


@router.get("/{entity_id}", response_model=EntityOut)
async def get_entity(entity_id: str, store: EntityStoreDep) -> EntityOut:
    return await store.get(entity_id)


@router.put("/{entity_id}", response_model=EntityOut)
async def update_entity(
    entity_id: str, data: EntityUpdate, store: EntityStoreDep
) -> EntityOut:
    return await store.update(entity_id, data)


@router.delete("/{entity_id}", status_code=204)
async def delete_entity(entity_id: str, store: EntityStoreDep) -> None:
    await store.delete(entity_id)


@router.put("/{entity_id}/icon", response_model=EntityOut)
async def set_entity_icon(
    entity_id: str, data: EntityIconSet, store: EntityStoreDep
) -> EntityOut:
    return await store.set_icon(entity_id, data.attachment_id)


@router.delete("/{entity_id}/icon", response_model=EntityOut)
async def clear_entity_icon(entity_id: str, store: EntityStoreDep) -> EntityOut:
    return await store.set_icon(entity_id, None)
