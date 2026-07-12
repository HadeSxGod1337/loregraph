from datetime import datetime

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    agent_instructions: str | None = None


class ProjectUpdate(BaseModel):
    name: str
    description: str | None = None
    agent_instructions: str | None = None


class ProjectOut(BaseModel):
    id: str
    name: str
    description: str | None
    agent_instructions: str | None
    created_at: datetime
    updated_at: datetime
