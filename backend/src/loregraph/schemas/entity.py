from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, model_validator

DEFAULT_ENTITY_TYPES = ("npc", "location", "faction", "item", "session")


class FieldType(StrEnum):
    TEXT = "text"
    RICH_TEXT = "rich_text"
    NUMBER = "number"
    BOOLEAN = "boolean"
    TAG = "tag"
    ATTACHMENT = "attachment"


class AttachmentRef(BaseModel):
    attachment_id: str
    url: str


class EntityFieldIn(BaseModel):
    key: str
    field_type: FieldType
    value: Any
    show_on_card: bool = False
    # Whitelist for limited player access: a field is shown to players only
    # when the DM explicitly flips this on. It lives inside the fields JSON, so
    # no DB migration is needed and old rows read back as False (deny by
    # default). Connectors and the vector index only read key/field_type/value,
    # so this flag never leaks through export or grounding.
    visible_to_players: bool = False

    @model_validator(mode="after")
    def check_value_matches_type(self) -> "EntityFieldIn":
        self.value = _coerce_field_value(self.field_type, self.value)
        return self


class EntityFieldOut(EntityFieldIn):
    pass


def _coerce_field_value(field_type: FieldType, value: object) -> object:
    if field_type is FieldType.TEXT:
        if not isinstance(value, str):
            raise ValueError("text field requires a string value")
        return value
    if field_type is FieldType.RICH_TEXT:
        if not isinstance(value, dict) or "type" not in value:
            raise ValueError(
                "rich_text field requires a ProseMirror doc object with a 'type' key"
            )
        return value
    if field_type is FieldType.NUMBER:
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise ValueError("number field requires an int or float value")
        return value
    if field_type is FieldType.BOOLEAN:
        if not isinstance(value, bool):
            raise ValueError("boolean field requires a bool value")
        return value
    if field_type is FieldType.TAG:
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ValueError("tag field requires a list of strings")
        return value
    if field_type is FieldType.ATTACHMENT:
        return AttachmentRef.model_validate(value)
    raise ValueError(f"Unknown field_type: {field_type}")


class EntityCreate(BaseModel):
    type: str
    title: str
    fields: list[EntityFieldIn] = []
    template_id: str | None = None


class EntityUpdate(BaseModel):
    type: str
    title: str
    fields: list[EntityFieldIn] = []
    template_id: str | None = None


class EntityOut(BaseModel):
    id: str
    project_id: str
    type: str
    title: str
    fields: list[EntityFieldOut]
    template_id: str | None = None
    icon: AttachmentRef | None = None
    pos_x: float | None = None
    pos_y: float | None = None
    # Limited player access: whether the whole party can see this entity, and
    # the separate text the DM wrote for them (a ProseMirror doc). Strict bool
    # on the way out even though the column is nullable — NULL reads as "not
    # revealed", so the frontend toggle is never left indeterminate.
    revealed_to_players: bool = False
    player_text: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class EntityIconSet(BaseModel):
    attachment_id: str


class EntityPositionEntry(BaseModel):
    entity_id: str
    pos_x: float
    pos_y: float


class EntityPlayerViewUpdate(BaseModel):
    """Everything about what players see, in one atomic write. Kept off
    EntityUpdate (which replaces the whole row) so a plain title/fields save
    from the editor can never silently wipe player_text — the same reason
    icon and positions have their own endpoints."""

    revealed_to_players: bool
    player_text: dict[str, Any] | None = None
    # Field keys to expose to players; every other field stays hidden.
    visible_field_keys: list[str] = []
