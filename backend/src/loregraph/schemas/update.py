from datetime import datetime
from typing import Literal

from pydantic import BaseModel

# How the launcher behaves when it finds a newer version on the remote:
# - "ask"   — show what changed and wait for an answer (the default)
# - "auto"  — pull without asking (the pre-0.3 behaviour)
# - "never" — don't even check
type UpdateMode = Literal["ask", "auto", "never"]

DEFAULT_UPDATE_MODE: UpdateMode = "ask"


class UpdatePreferences(BaseModel):
    """What the user decided about updates. Owned by both the app and the
    launcher scripts, which is why it is persisted as a flat key=value file
    (see services/update_status.py) rather than JSON: the launcher reads it
    before uv/Node are guaranteed to exist."""

    mode: UpdateMode = DEFAULT_UPDATE_MODE
    # Versions the user explicitly chose to pass on. A skipped version stops
    # being offered, but a *newer* one is offered again.
    skipped_versions: list[str] = []


class UpdateStatusOut(BaseModel):
    """Result of the launcher's last update check, plus the current
    preferences. The backend never talks to the git remote itself — it only
    reads what the launcher wrote (see UpdateService)."""

    current_version: str
    # False = no .git / no git binary (zip install): checking is impossible,
    # and the UI says so instead of pretending everything is up to date.
    git_available: bool = False
    # True = local changes block a fast-forward pull; the user has to deal
    # with them first, so the UI offers no "update" affordance.
    worktree_dirty: bool = False
    latest_version: str | None = None
    update_available: bool = False
    # The remote CHANGELOG section for latest_version, raw markdown.
    changelog: str | None = None
    checked_at: datetime | None = None
    preferences: UpdatePreferences
