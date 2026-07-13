import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from loregraph.exceptions import ProjectNotFoundError
from loregraph.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate
from loregraph.storage.sqlite.models import EdgeRow, EntityRow, ProjectRow


class SqliteProjectStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_projects(self) -> list[ProjectOut]:
        entity_counts = await self._counts_by_project(EntityRow.project_id)
        edge_counts = await self._counts_by_project(EdgeRow.project_id)
        rows = (await self._session.execute(select(ProjectRow))).scalars().all()
        return [
            _row_to_out(
                row,
                entity_count=entity_counts.get(row.id, 0),
                edge_count=edge_counts.get(row.id, 0),
            )
            for row in rows
        ]

    async def _counts_by_project(
        self, project_id_column: InstrumentedAttribute[str]
    ) -> dict[str, int]:
        result = await self._session.execute(
            select(project_id_column, func.count()).group_by(project_id_column)
        )
        return {project_id: count for project_id, count in result.all()}

    async def create(self, data: ProjectCreate) -> ProjectOut:
        now = datetime.now(UTC)
        row = ProjectRow(
            id=uuid.uuid4().hex,
            name=data.name,
            description=data.description,
            agent_instructions=data.agent_instructions,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.commit()
        return _row_to_out(row)

    async def get(self, project_id: str) -> ProjectOut:
        row = await self._session.get(ProjectRow, project_id)
        if row is None:
            raise ProjectNotFoundError(project_id)
        return _row_to_out(row)

    async def update(self, project_id: str, data: ProjectUpdate) -> ProjectOut:
        row = await self._session.get(ProjectRow, project_id)
        if row is None:
            raise ProjectNotFoundError(project_id)
        row.name = data.name
        row.description = data.description
        row.agent_instructions = data.agent_instructions
        row.updated_at = datetime.now(UTC)
        await self._session.commit()
        return _row_to_out(row)

    async def delete(self, project_id: str) -> None:
        row = await self._session.get(ProjectRow, project_id)
        if row is None:
            raise ProjectNotFoundError(project_id)
        await self._session.delete(row)
        await self._session.commit()

    async def exists(self, project_id: str) -> bool:
        return await self._session.get(ProjectRow, project_id) is not None


def _row_to_out(
    row: ProjectRow, entity_count: int = 0, edge_count: int = 0
) -> ProjectOut:
    return ProjectOut(
        id=row.id,
        name=row.name,
        description=row.description,
        agent_instructions=row.agent_instructions,
        entity_count=entity_count,
        edge_count=edge_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
