from typing import Annotated

from fastapi import APIRouter, Query

from loregraph.api.deps import EntityServiceDep, EventBusDep
from loregraph.schemas.entity import (
    EntityCreate,
    EntityIconSet,
    EntityOut,
    EntityPlayerViewUpdate,
    EntityPositionEntry,
    EntityUpdate,
)
from loregraph.services.event_bus import EVENT_WORLD_PLAYER_VIEW_CHANGED

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


@router.put("/positions", response_model=list[EntityOut])
async def update_positions(
    project_id: str, positions: list[EntityPositionEntry], service: EntityServiceDep
) -> list[EntityOut]:
    """Batch-save node positions (drag-end, or "Reset Layout" touching many
    nodes at once). Registered before `/{entity_id}` on purpose — Starlette
    matches routes in registration order, and `/{entity_id}` would otherwise
    swallow requests to `/positions` first."""
    return await service.update_positions(project_id, positions)


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


@router.put("/{entity_id}/player-view", response_model=EntityOut)
async def set_entity_player_view(
    project_id: str,
    entity_id: str,
    data: EntityPlayerViewUpdate,
    service: EntityServiceDep,
    event_bus: EventBusDep,
) -> EntityOut:
    """DM-only: reveal/hide an entity for players, set the player-facing text,
    and choose which fields players may see — all in one atomic write, kept
    off EntityUpdate so a normal save can't wipe it. Publishes a realtime
    event so open DM tabs refresh live."""
    entity = await service.set_player_view(project_id, entity_id, data)
    event_bus.publish(
        project_id,
        EVENT_WORLD_PLAYER_VIEW_CHANGED,
        entity_id=entity_id,
        revealed=entity.revealed_to_players,
    )
    return entity
