import secrets

from fastapi import APIRouter

from loregraph.api.deps import (
    EntityServiceDep,
    NetworkStatusDep,
    PlayerNoteStoreDep,
    PlayerStoreDep,
    ProjectStoreDep,
)
from loregraph.api.security import hash_token
from loregraph.exceptions import PlayerNotFoundError
from loregraph.schemas.player import (
    PlayerCreate,
    PlayerCreatedOut,
    PlayerNoteOut,
    PlayerOut,
)
from loregraph.services.network import NetworkStatus

router = APIRouter(prefix="/projects/{project_id}", tags=["players"])


@router.get("/players", response_model=list[PlayerOut])
async def list_players(
    project_id: str,
    project_store: ProjectStoreDep,
    player_store: PlayerStoreDep,
    note_store: PlayerNoteStoreDep,
) -> list[PlayerOut]:
    await project_store.get(project_id)  # 404 for unknown projects
    players = await player_store.list_for_project(project_id)
    counts = await note_store.count_by_player(project_id)
    # No play_url in the list: the raw token is never stored, so a full link
    # only exists at create/rotate time. The prefix and status are enough here.
    for player in players:
        player.note_count = counts.get(player.id, 0)
    return players


@router.post("/players", response_model=PlayerCreatedOut, status_code=201)
async def create_player(
    project_id: str,
    data: PlayerCreate,
    project_store: ProjectStoreDep,
    player_store: PlayerStoreDep,
    network: NetworkStatusDep,
) -> PlayerCreatedOut:
    await project_store.get(project_id)
    token = secrets.token_urlsafe(32)
    player = await player_store.create(
        project_id, data.name, hash_token(token), token[:8]
    )
    return _with_token(player, token, network)


@router.post("/players/{player_id}/rotate", response_model=PlayerCreatedOut)
async def rotate_player_token(
    project_id: str,
    player_id: str,
    player_store: PlayerStoreDep,
    network: NetworkStatusDep,
) -> PlayerCreatedOut:
    """Issue a new link and kill the old one — for a leaked or lost invite."""
    await _require_in_project(player_store, project_id, player_id)
    token = secrets.token_urlsafe(32)
    player = await player_store.set_token(player_id, hash_token(token), token[:8])
    return _with_token(player, token, network)


@router.post("/players/{player_id}/revoke", response_model=PlayerOut)
async def revoke_player(
    project_id: str, player_id: str, player_store: PlayerStoreDep
) -> PlayerOut:
    """Disable the link but keep the player's notes (unlike delete)."""
    await _require_in_project(player_store, project_id, player_id)
    return await player_store.set_revoked(player_id, True)


@router.delete("/players/{player_id}", status_code=204)
async def delete_player(
    project_id: str, player_id: str, player_store: PlayerStoreDep
) -> None:
    """Irreversible: the player's notes cascade away with them (revoke keeps
    them). The UI guards this behind a typed confirmation."""
    await _require_in_project(player_store, project_id, player_id)
    await player_store.delete(player_id)


@router.get("/entities/{entity_id}/player-notes", response_model=list[PlayerNoteOut])
async def list_entity_player_notes(
    project_id: str,
    entity_id: str,
    service: EntityServiceDep,
    note_store: PlayerNoteStoreDep,
) -> list[PlayerNoteOut]:
    """Every note on an entity, including private ones — the DM sees all."""
    await service.get_in_project(project_id, entity_id)
    records = await note_store.list_for_entity(entity_id)
    # viewer_player_id=None: the DM is not a player, so nothing reads as "own".
    return [PlayerNoteOut.from_record(r, viewer_player_id=None) for r in records]


async def _require_in_project(
    player_store: PlayerStoreDep, project_id: str, player_id: str
) -> None:
    player = await player_store.get(player_id)
    if player.project_id != project_id:
        # Wrong project -> 404, never confirm the id exists elsewhere.
        raise PlayerNotFoundError(player_id)


def _with_token(
    player: PlayerOut, token: str, network: NetworkStatus
) -> PlayerCreatedOut:
    # The address comes from the live network status, not raw settings: in
    # internet mode that is the public address the router reported, so the link
    # a player is handed is the one that actually reaches this machine.
    return PlayerCreatedOut(
        **player.model_dump(exclude={"play_url"}),
        token=token,
        play_url=f"{network.base_url}/play/{token}",
    )
