"""Runtime configuration: the effective `Settings` the app is running with
right now, and the rules for changing it from the UI.

Layering is `stored override > .env / process env > field default`. The UI is
the later and more explicit decision, so it wins; `.env` stays the bootstrap
path (the launcher wizard, Docker) and the API reports, per field, which layer
a value came from — otherwise "I edited .env and nothing happened" is
unexplainable.

The `Settings` instance itself stays immutable: an update builds a new one and
swaps it in atomically, so a request that already read the old one keeps a
consistent view for its whole lifetime.
"""

import asyncio
import logging
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import TypeAdapter, ValidationError

from loregraph.config import (
    SECRET_SETTINGS_FIELDS,
    UI_EDITABLE_FIELDS,
    Settings,
)
from loregraph.exceptions import SettingsFieldInvalidError, SettingsFieldUnknownError

logger = logging.getLogger(__name__)

type SettingSource = Literal["db", "env", "default"]


def validate_override(field_name: str, value: Any) -> Any:
    """Coerce one incoming value to the type its `Settings` field declares.

    Per-field (rather than re-validating a whole Settings object) for two
    reasons: the error names the offending field, and rebuilding a
    BaseSettings would re-read the environment, quietly resurrecting values
    the user just cleared.
    """
    if field_name not in UI_EDITABLE_FIELDS:
        raise SettingsFieldUnknownError(field_name)
    field = Settings.model_fields[field_name]
    try:
        return TypeAdapter(field.annotation).validate_python(value)
    except ValidationError as e:
        raise SettingsFieldInvalidError(field_name, _first_error(e)) from e


def _first_error(error: ValidationError) -> str:
    details = error.errors()
    # Only the message, never the input: a rejected value may be an API key.
    return details[0]["msg"] if details else "invalid value"


def sanitize_stored(stored: Mapping[str, Any]) -> dict[str, Any]:
    """Drop anything the whitelist doesn't cover, on read as well as on write.

    A row that predates a field being removed — or one written by hand —
    must not be able to reach a launch/security setting like `trust_loopback`.
    """
    clean: dict[str, Any] = {}
    for key, value in stored.items():
        if key not in UI_EDITABLE_FIELDS:
            logger.warning("Ignoring stored setting %r: not UI-editable", key)
            continue
        try:
            clean[key] = validate_override(key, value)
        except (SettingsFieldUnknownError, SettingsFieldInvalidError):
            logger.warning("Ignoring stored setting %r: invalid value", key)
    return clean


class SettingsProvider:
    """Holds the effective settings and the overrides they were built from."""

    def __init__(
        self, base: Settings, overrides: Mapping[str, Any] | None = None
    ) -> None:
        self._base = base
        self._overrides: dict[str, Any] = dict(overrides or {})
        self._current = self._compose()
        self._lock = asyncio.Lock()

    def _compose(self) -> Settings:
        # model_copy, not Settings(**...): values are already validated field
        # by field, and re-running the settings sources would re-read env.
        return self._base.model_copy(update=self._overrides)

    @property
    def current(self) -> Settings:
        return self._current

    @property
    def base(self) -> Settings:
        """Settings as env and defaults alone define them — what a reset
        restores a field to."""
        return self._base

    @property
    def overrides(self) -> dict[str, Any]:
        return dict(self._overrides)

    @property
    def lock(self) -> asyncio.Lock:
        """Serializes read-modify-write of the settings across requests; the
        settings router also holds it while rebuilding the embedding stack, so
        two concurrent saves can't interleave into a torn configuration."""
        return self._lock

    def source_of(self, field_name: str) -> SettingSource:
        if field_name in self._overrides:
            return "db"
        # model_fields_set on a BaseSettings holds exactly the fields some
        # source (.env, process env, explicit kwarg) actually supplied.
        if field_name in self._base.model_fields_set:
            return "env"
        return "default"

    def replace_overrides(self, overrides: Mapping[str, Any]) -> Settings:
        self._overrides = dict(overrides)
        self._current = self._compose()
        return self._current


def is_secret_field(field_name: str) -> bool:
    return field_name in SECRET_SETTINGS_FIELDS
