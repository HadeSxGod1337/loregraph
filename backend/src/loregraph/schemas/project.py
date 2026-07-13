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
    # Populated by list_projects (project cards show world size at a glance);
    # single-project reads leave the defaults — callers there have the real
    # entities/edges loaded anyway.
    entity_count: int = 0
    edge_count: int = 0
    created_at: datetime
    updated_at: datetime
