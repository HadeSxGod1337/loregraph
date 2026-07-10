from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, model_validator

DEFAULT_ENTITY_TYPES = ("npc", "location", "faction", "item", "session")


class FieldType(StrEnum):
    TEXT = "text"
    RICH_TEXT = "rich_text"
    NUMBER = "number"
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


class EntityUpdate(BaseModel):
    type: str
    title: str
    fields: list[EntityFieldIn] = []


class EntityOut(BaseModel):
    id: str
    project_id: str
    type: str
    title: str
    fields: list[EntityFieldOut]
    icon: AttachmentRef | None = None
    created_at: datetime
    updated_at: datetime


class EntityIconSet(BaseModel):
    attachment_id: str
