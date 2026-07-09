from datetime import datetime

from pydantic import BaseModel


class AttachmentOut(BaseModel):
    id: str
    entity_id: str
    url: str
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: datetime
