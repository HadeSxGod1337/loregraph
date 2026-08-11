from fastapi import APIRouter

from loregraph.api.deps import UpdateServiceDep
from loregraph.schemas.update import UpdatePreferences, UpdateStatusOut

router = APIRouter(prefix="/updates", tags=["updates"])


@router.get("", response_model=UpdateStatusOut)
async def get_update_status(update_service: UpdateServiceDep) -> UpdateStatusOut:
    """What the launcher found the last time it checked, plus preferences.

    There is no "check now": the launcher owns the network access to the git
    remote (see services/update_status.py), so freshness is bounded by its
    10-minute loop — `checked_at` tells the UI how stale this is."""
    return update_service.read_status()


@router.put("/preferences", response_model=UpdatePreferences)
async def set_update_preferences(
    prefs: UpdatePreferences, update_service: UpdateServiceDep
) -> UpdatePreferences:
    """Takes effect on the next launch — the launcher reads the same file."""
    return update_service.write_preferences(prefs)
