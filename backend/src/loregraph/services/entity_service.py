import logging

from loregraph.exceptions import EntityNotFoundError
from loregraph.schemas.entity import (
    EntityCreate,
    EntityOut,
    EntityPositionEntry,
    EntityUpdate,
)
from loregraph.services.vector_index import VectorIndex
from loregraph.storage.protocols import EntityStore

logger = logging.getLogger(__name__)


class EntityService:
    """Single write path for entities.

    REST routers, MCP tools, and the agent's commit node all go through this
    class, so project-scoping rules and vector-store indexing can never
    diverge between the three callers.
    """

    def __init__(
        self, store: EntityStore, vector_index: VectorIndex | None = None
    ) -> None:
        self._store = store
        self._vector_index = vector_index

    async def list_entities(
        self, project_id: str, entity_type: str | None = None
    ) -> list[EntityOut]:
        return await self._store.list_entities(project_id, entity_type=entity_type)

    async def get_in_project(self, project_id: str, entity_id: str) -> EntityOut:
        entity = await self._store.get(entity_id)
        if entity.project_id != project_id:
            # Wrong project for this id — 404, not 403: don't confirm the id
            # exists at all outside its own project.
            raise EntityNotFoundError(entity_id)
        return entity

    async def create(self, data: EntityCreate, project_id: str) -> EntityOut:
        entity = await self._store.create(data, project_id)
        await self._index_safely(entity)
        return entity

    async def update(
        self, project_id: str, entity_id: str, data: EntityUpdate
    ) -> EntityOut:
        await self.get_in_project(project_id, entity_id)
        entity = await self._store.update(entity_id, data)
        await self._index_safely(entity)
        return entity

    async def delete(self, project_id: str, entity_id: str) -> None:
        await self.get_in_project(project_id, entity_id)
        await self._store.delete(entity_id)
        if self._vector_index is not None:
            try:
                await self._vector_index.remove_entity(project_id, entity_id)
            except Exception:
                logger.warning(
                    "Vector de-indexing failed for entity %s; "
                    "run a project reindex to repair.",
                    entity_id,
                    exc_info=True,
                )

    async def set_icon(
        self, project_id: str, entity_id: str, attachment_id: str | None
    ) -> EntityOut:
        await self.get_in_project(project_id, entity_id)
        return await self._store.set_icon(entity_id, attachment_id)

    async def update_positions(
        self, project_id: str, positions: list[EntityPositionEntry]
    ) -> list[EntityOut]:
        # Same project-scoping guarantee as update()/set_icon(): every entity
        # in the batch must belong to this project before any write happens.
        for entry in positions:
            await self.get_in_project(project_id, entry.entity_id)
        return await self._store.update_positions(positions)

    async def _index_safely(self, entity: EntityOut) -> None:
        # The index is derived data — never fail the committed SQL write over
        # it (docs/agent_architecture.md, section 4). CancelledError is a
        # BaseException and propagates past this handler by design.
        if self._vector_index is None:
            return
        try:
            await self._vector_index.index_entity(entity)
        except Exception:
            logger.warning(
                "Vector indexing failed for entity %s; "
                "run a project reindex to repair.",
                entity.id,
                exc_info=True,
            )
