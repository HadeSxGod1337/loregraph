from pydantic import BaseModel

from loregraph.schemas.entity import EntityFieldOut

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
