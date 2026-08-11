from fastapi import APIRouter, Response

from loregraph.api.deps import (
    PlayerIdentityDep,
    PlayerStoreDep,
    PlayerViewServiceDep,
    ProjectStoreDep,
)
from loregraph.api.security import PLAY_COOKIE_NAME, hash_token
from loregraph.exceptions import InvalidPlayerTokenError
from loregraph.schemas.play import (
    PlayerEntityOut,
    PlayerSubgraphOut,
    PlaySessionOut,
    PlaySessionRequest,
)
from loregraph.schemas.player import PlayerNoteOut, PlayerNoteWrite

# Everything except POST /session is player-guarded. The project is always
# taken from the identity, never the URL, so a token can't reach another world.
router = APIRouter(prefix="/play", tags=["play"])


@router.post("/session", response_model=PlaySessionOut)
async def start_session(
    data: PlaySessionRequest,
    response: Response,
    player_store: PlayerStoreDep,
    project_store: ProjectStoreDep,
) -> PlaySessionOut:
    """Exchange a play token for a session cookie. The raw token is kept in the
    cookie itself (HttpOnly), so <img> and WebSocket subresource requests carry
    it without a header, and revocation still works through the same hash
    lookup — no separate session store to keep in sync."""
    player = await player_store.find_active_by_token_hash(hash_token(data.token))
    if player is None:
        raise InvalidPlayerTokenError()
    project = await project_store.get(player.project_id)
    response.set_cookie(
        key=PLAY_COOKIE_NAME,
        value=data.token,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return PlaySessionOut(
        player_id=player.id,
        project_id=player.project_id,
        project_name=project.name,
        name=player.name,
    )


@router.delete("/session", status_code=204)
async def end_session(response: Response) -> None:
    response.delete_cookie(PLAY_COOKIE_NAME, path="/")


@router.get("/me", response_model=PlaySessionOut)
async def get_me(
    identity: PlayerIdentityDep, project_store: ProjectStoreDep
) -> PlaySessionOut:
    project = await project_store.get(identity.project_id)
    return PlaySessionOut(
        player_id=identity.player_id,
        project_id=identity.project_id,
        project_name=project.name,
        name=identity.name,
    )


@router.get("/entities", response_model=list[PlayerEntityOut])
async def list_entities(
    identity: PlayerIdentityDep, service: PlayerViewServiceDep
) -> list[PlayerEntityOut]:
    return await service.list_revealed(identity.project_id)


@router.get("/entities/{entity_id}", response_model=PlayerEntityOut)
async def get_entity(
    entity_id: str, identity: PlayerIdentityDep, service: PlayerViewServiceDep
) -> PlayerEntityOut:
    return await service.get_revealed(identity.project_id, entity_id)


@router.get("/graph", response_model=PlayerSubgraphOut)
async def get_graph(
    identity: PlayerIdentityDep, service: PlayerViewServiceDep
) -> PlayerSubgraphOut:
    return await service.revealed_subgraph(identity.project_id)


@router.get("/entities/{entity_id}/notes", response_model=list[PlayerNoteOut])
async def list_notes(
    entity_id: str, identity: PlayerIdentityDep, service: PlayerViewServiceDep
) -> list[PlayerNoteOut]:
    return await service.list_visible_notes(
        identity.project_id, entity_id, identity.player_id
    )


@router.post(
    "/entities/{entity_id}/notes", response_model=PlayerNoteOut, status_code=201
)
async def create_note(
    entity_id: str,
    data: PlayerNoteWrite,
    identity: PlayerIdentityDep,
    service: PlayerViewServiceDep,
) -> PlayerNoteOut:
    return await service.create_note(
        identity.project_id,
        entity_id,
        identity.player_id,
        data.body,
        data.is_public,
    )


@router.put("/notes/{note_id}", response_model=PlayerNoteOut)
async def update_note(
    note_id: str,
    data: PlayerNoteWrite,
    identity: PlayerIdentityDep,
    service: PlayerViewServiceDep,
) -> PlayerNoteOut:
    return await service.update_own_note(
        note_id, identity.player_id, data.body, data.is_public
    )


@router.delete("/notes/{note_id}", status_code=204)
async def delete_note(
    note_id: str, identity: PlayerIdentityDep, service: PlayerViewServiceDep
) -> None:
    await service.delete_own_note(note_id, identity.player_id)
