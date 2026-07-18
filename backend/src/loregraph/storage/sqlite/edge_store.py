import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.exceptions import EdgeNotFoundError
from loregraph.schemas.edge import EdgeCreate, EdgeOut, EdgeUpdate
from loregraph.storage.sqlite.models import EdgeRow


class SqliteEdgeStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, edge_id: str) -> EdgeOut:
        row = await self._session.get(EdgeRow, edge_id)
        if row is None:
            raise EdgeNotFoundError(edge_id)
        return _row_to_out(row)

    async def list_for_entity(self, entity_id: str) -> list[EdgeOut]:
        stmt = select(EdgeRow).where(
            or_(
                EdgeRow.source_entity_id == entity_id,
                EdgeRow.target_entity_id == entity_id,
            )
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_row_to_out(row) for row in rows]

    async def list_all(
        self, project_id: str, edge_types: frozenset[str] | None = None
    ) -> list[EdgeOut]:
        stmt = select(EdgeRow).where(EdgeRow.project_id == project_id)
        if edge_types is not None:
            stmt = stmt.where(EdgeRow.type.in_(edge_types))
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_row_to_out(row) for row in rows]

    async def create(self, data: EdgeCreate, project_id: str) -> EdgeOut:
        row = EdgeRow(
            id=uuid.uuid4().hex,
            project_id=project_id,
            source_entity_id=data.source_entity_id,
            target_entity_id=data.target_entity_id,
            type=data.type,
            label=data.label,
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.commit()
        return _row_to_out(row)

    async def update(self, edge_id: str, data: EdgeUpdate) -> EdgeOut:
        row = await self._session.get(EdgeRow, edge_id)
        if row is None:
            raise EdgeNotFoundError(edge_id)
        row.type = data.type
        row.label = data.label
        if data.reverse:
            row.source_entity_id, row.target_entity_id = (
                row.target_entity_id,
                row.source_entity_id,
            )
        await self._session.commit()
        return _row_to_out(row)

    async def delete(self, edge_id: str) -> None:
        row = await self._session.get(EdgeRow, edge_id)
        if row is None:
            raise EdgeNotFoundError(edge_id)
        await self._session.delete(row)
        await self._session.commit()


def _row_to_out(row: EdgeRow) -> EdgeOut:
    return EdgeOut(
        id=row.id,
        project_id=row.project_id,
        source_entity_id=row.source_entity_id,
        target_entity_id=row.target_entity_id,
        type=row.type,
        label=row.label,
        created_at=row.created_at,
    )
