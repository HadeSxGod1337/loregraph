from datetime import datetime

from pydantic import BaseModel


class KnowledgeSourceOut(BaseModel):
    id: str
    project_id: str
    original_filename: str
    content_type: str
    size_bytes: int
    status: str
    error: str | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime
