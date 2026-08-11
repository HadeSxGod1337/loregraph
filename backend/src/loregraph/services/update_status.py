"""Update preferences and the launcher's last check result.

The backend deliberately does **not** talk to the git remote. The launcher
(scripts/start.ps1 / scripts/start.sh) already fetches at startup and every
10 minutes — it is the single owner of network access to the remote. Making
the server shell out to git too would mean a second source of truth, a race
for .git/index.lock with the user's own git, and a phone-home the user never
opted into. So the launcher writes, the backend reads.

The on-disk format is flat `key=value`, not JSON, because the launcher parses
it *before* uv and Node are guaranteed to be installed: no Python, no jq. The
changelog section lives in its own file so neither shell has to escape
multi-line markdown.
"""

import logging
import os
from collections.abc import Mapping
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from loregraph.schemas.update import (
    DEFAULT_UPDATE_MODE,
    UpdateMode,
    UpdatePreferences,
    UpdateStatusOut,
)

logger = logging.getLogger(__name__)

UPDATE_PREFS_FILENAME = "update.conf"
UPDATE_STATUS_FILENAME = "update-status.conf"
UPDATE_CHANGELOG_FILENAME = "update-changelog.md"

_PREFS_HEADER = (
    "# Loregraph update preferences.\n"
    "# Edit here or in the app (sidebar -> preferences -> updates).\n"
    "# mode: ask | auto | never\n"
)
_VALID_MODES: frozenset[str] = frozenset(("ask", "auto", "never"))
_UNKNOWN_VERSION = "0.0.0+unknown"


def app_version() -> str:
    """The running app's version, read from installed package metadata.

    Not a fifth hardcoded copy: the version already lives in pyproject.toml,
    package.json, uv.lock and the git tag (scripts/check-version.sh keeps
    those in sync)."""
    try:
        return version("loregraph")
    except PackageNotFoundError:
        # Running from a source tree that was never `uv sync`ed.
        logger.debug("loregraph package metadata not found; version unknown")
        return _UNKNOWN_VERSION


def read_key_values(path: Path) -> dict[str, str]:
    """Parse a `key=value` file written by the launcher.

    Deliberately tolerant: a half-written, hand-edited or truncated file must
    degrade to "I don't know" rather than take the app down. Values may
    contain `=` (only the first one splits); `#` starts a comment line."""
    try:
        # utf-8-sig: PowerShell is asked to write BOM-less UTF-8, but a
        # hand-edited file may well come back with a BOM.
        raw = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {}
    except OSError:
        logger.warning("Could not read %s", path, exc_info=True)
        return {}
    values: dict[str, str] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


def write_key_values(
    path: Path, values: Mapping[str, str], *, header: str = ""
) -> None:
    """Write a `key=value` file atomically (temp file + rename).

    The launcher may read this file at any moment; a partial write would look
    like a corrupt config to a shell parser that has no way to tell."""
    body = header + "".join(f"{key}={value}\n" for key, value in values.items())
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(body, encoding="utf-8", newline="\n")
    os.replace(tmp_path, path)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return None
    except OSError:
        logger.warning("Could not read %s", path, exc_info=True)
        return None


def _parse_bool(value: str | None) -> bool:
    return value is not None and value.strip().lower() in ("1", "true", "yes")


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        logger.debug("Ignoring unparseable update check timestamp %r", value)
        return None


def _parse_mode(value: str | None) -> UpdateMode:
    if value in _VALID_MODES:
        # The frozenset membership check above is what narrows this to the
        # Literal; mypy can't see through a runtime set, hence the ignore.
        return value  # type: ignore[return-value]
    return DEFAULT_UPDATE_MODE


def _parse_versions(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


class UpdateService:
    """Reads (and writes) the update files under the app's data directory."""

    def __init__(self, data_dir: Path, current_version: str) -> None:
        self._data_dir = data_dir
        self._current_version = current_version

    @property
    def _prefs_path(self) -> Path:
        return self._data_dir / UPDATE_PREFS_FILENAME

    @property
    def _status_path(self) -> Path:
        return self._data_dir / UPDATE_STATUS_FILENAME

    @property
    def _changelog_path(self) -> Path:
        return self._data_dir / UPDATE_CHANGELOG_FILENAME

    def read_preferences(self) -> UpdatePreferences:
        values = read_key_values(self._prefs_path)
        return UpdatePreferences(
            mode=_parse_mode(values.get("mode")),
            skipped_versions=_parse_versions(values.get("skipped_versions")),
        )

    def write_preferences(self, prefs: UpdatePreferences) -> UpdatePreferences:
        write_key_values(
            self._prefs_path,
            {
                "mode": prefs.mode,
                "skipped_versions": ",".join(prefs.skipped_versions),
            },
            header=_PREFS_HEADER,
        )
        return prefs

    def read_status(self) -> UpdateStatusOut:
        values = read_key_values(self._status_path)
        prefs = self.read_preferences()
        latest = values.get("latest_version") or None
        git_available = _parse_bool(values.get("git_available"))
        update_available = bool(
            git_available
            and latest is not None
            and latest != self._current_version
            and latest not in prefs.skipped_versions
        )
        return UpdateStatusOut(
            current_version=self._current_version,
            git_available=git_available,
            worktree_dirty=_parse_bool(values.get("worktree_dirty")),
            latest_version=latest,
            update_available=update_available,
            changelog=_read_text(self._changelog_path) if update_available else None,
            checked_at=_parse_datetime(values.get("checked_at")),
            preferences=prefs,
        )
