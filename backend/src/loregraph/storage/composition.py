from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.storage.protocols import (
    AgentSessionStore,
    AttachmentStore,
    EdgeStore,
    EntityStore,
    KnowledgeSourceStore,
    ProjectStore,
)


@dataclass(frozen=True)
class StoreFactories:
    """The one place that knows which concrete class implements each storage
    Protocol for a given AsyncSession. Built once in main.py's composition
    root; api/deps.py consumes it without ever importing a concrete store."""

    project: Callable[[AsyncSession], ProjectStore]
    entity: Callable[[AsyncSession], EntityStore]
    edge: Callable[[AsyncSession], EdgeStore]
    attachment: Callable[[AsyncSession], AttachmentStore]
    agent_session: Callable[[AsyncSession], AgentSessionStore]
    knowledge_source: Callable[[AsyncSession], KnowledgeSourceStore]
