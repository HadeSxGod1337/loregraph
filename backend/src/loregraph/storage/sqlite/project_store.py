import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.exceptions import ProjectNotFoundError
from loregraph.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate
from loregraph.storage.sqlite.models import ProjectRow


class SqliteProjectStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_projects(self) -> list[ProjectOut]:
        rows = (await self._session.execute(select(ProjectRow))).scalars().all()
        return [_row_to_out(row) for row in rows]

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


def _row_to_out(row: ProjectRow) -> ProjectOut:
    return ProjectOut(
        id=row.id,
        name=row.name,
        description=row.description,
        agent_instructions=row.agent_instructions,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
