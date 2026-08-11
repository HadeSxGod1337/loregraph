from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from loregraph.api.deps import EntityStoreDep, IdentityDep, SettingsDep
from loregraph.api.security import PlayerIdentity
from loregraph.exceptions import EntityNotFoundError

router = APIRouter(tags=["files"])


@router.get("/files/{entity_id}/{filename}")
async def get_attachment_file(
    entity_id: str,
    filename: str,
    identity: IdentityDep,
    entity_store: EntityStoreDep,
    settings: SettingsDep,
) -> FileResponse:
    """Serve an entity attachment behind the access layer.

    This replaces a bare StaticFiles mount, which bypassed every router guard —
    once the app listens beyond loopback, that mount would hand any file to
    anyone on the network. StaticFiles also gave path-traversal protection for
    free; with an explicit route that has to be written by hand, hence the
    name checks below. Players may only fetch files of an entity that is
    revealed and in their own project."""
    # Traversal guard: reject anything that isn't a single path segment, so
    # "../../campaign.sqlite3" can never escape the attachments directory.
    if _unsafe(entity_id) or _unsafe(filename):
        raise HTTPException(status_code=404, detail="Not found")

    try:
        entity = await entity_store.get(entity_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Not found") from exc

    if isinstance(identity, PlayerIdentity):
        # 404, not 403: don't confirm a hidden entity or another project exists.
        if entity.project_id != identity.project_id or not entity.revealed_to_players:
            raise HTTPException(status_code=404, detail="Not found")

    path = (settings.attachments_dir / entity_id / filename).resolve()
    root = settings.attachments_dir.resolve()
    # Belt-and-suspenders against symlinks/normalization surprises.
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")

    return FileResponse(path)


def _unsafe(segment: str) -> bool:
    from pathlib import PurePosixPath, PureWindowsPath

    # A safe segment is exactly its own basename on both path flavours and has
    # no separators or drive/root parts.
    return (
        not segment
        or PurePosixPath(segment).name != segment
        or PureWindowsPath(segment).name != segment
    )
