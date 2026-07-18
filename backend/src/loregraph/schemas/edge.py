from datetime import datetime

from pydantic import BaseModel


class EdgeCreate(BaseModel):
    source_entity_id: str
    target_entity_id: str
    type: str
    label: str | None = None


class EdgeUpdate(BaseModel):
    type: str
    label: str | None = None
    # Swaps source_entity_id/target_entity_id; this schema has no way to
    # retarget an edge to a different entity, only flip its direction.
    reverse: bool = False


class EdgeOut(BaseModel):
    id: str
    project_id: str
    source_entity_id: str
    target_entity_id: str
    type: str
    label: str | None
    created_at: datetime
