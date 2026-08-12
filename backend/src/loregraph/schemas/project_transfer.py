from typing import Any

from pydantic import BaseModel

from loregraph.schemas.entity import EntityFieldOut
from loregraph.schemas.entity_template import EntityTemplateBase
from loregraph.schemas.sheet_preset import SheetPresetBase

FORMAT_VERSION = 1


class ProjectExportAttachment(BaseModel):
    id: str
    entity_id: str
    original_filename: str
    stored_filename: str
    content_type: str
    data_base64: str


class ProjectExportEntity(BaseModel):
    id: str
    type: str
    title: str
    fields: list[EntityFieldOut]
    # Optional so export files written before sheet templates existed still
    # import cleanly; a built-in template id survives the round trip because
    # built-ins are code, not per-project rows.
    template_id: str | None = None
    icon_attachment_id: str | None = None
    pos_x: float | None = None
    pos_y: float | None = None
    # Limited player access. Defaulted so files exported before this existed
    # import cleanly (everything hidden). Players and their notes are NOT part
    # of an export — tokens and personal notes must not travel in a file.
    revealed_to_players: bool = False
    player_text: dict[str, Any] | None = None


class ProjectExportTemplate(EntityTemplateBase):
    """A project's own entity template, carried whole so its sheet survives the
    move. Only project templates travel: built-ins are code, present in every
    install under the same fixed id, so an entity bound to one re-binds itself
    on arrival. The id here is the *source* id — import allocates a new one and
    rewrites every entity's template_id through the map (ids are never reused,
    same rule as entities)."""

    id: str


class ProjectExportPreset(SheetPresetBase):
    """A project's own sheet preset — same reasoning as ProjectExportTemplate.
    Presets are referenced by nothing once inserted into a layout (the designer
    copies their fields and section in), so no id remapping is needed; the id
    rides along only to keep the file self-describing."""

    id: str


class ProjectExportEdge(BaseModel):
    source_entity_id: str
    target_entity_id: str
    type: str
    label: str | None = None


class ProjectExport(BaseModel):
    format_version: int = FORMAT_VERSION
    name: str
    description: str | None = None
    entities: list[ProjectExportEntity]
    edges: list[ProjectExportEdge]
    attachments: list[ProjectExportAttachment] = []
    # Defaulted rather than version-bumped: FORMAT_VERSION stays 1 so files
    # written before templates existed still import (they simply carry none),
    # and a file written now still opens in a build that predates the field —
    # Pydantic ignores what it does not know. An older build loses the layouts,
    # which is exactly what it did before this field existed.
    templates: list[ProjectExportTemplate] = []
    sheet_presets: list[ProjectExportPreset] = []
