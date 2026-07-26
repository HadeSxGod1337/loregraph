import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.exceptions import SheetPresetNotFoundError
from loregraph.schemas.entity_template import Section, TemplateFieldDef
from loregraph.schemas.sheet_preset import SheetPresetCreate, SheetPresetOut
from loregraph.storage.sqlite.models import SheetPresetRow


class SqliteSheetPresetStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_project(self, project_id: str) -> list[SheetPresetOut]:
        stmt = select(SheetPresetRow).where(SheetPresetRow.project_id == project_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_row_to_out(row) for row in rows]

    async def get(self, preset_id: str) -> SheetPresetOut:
        row = await self._session.get(SheetPresetRow, preset_id)
        if row is None:
            raise SheetPresetNotFoundError(preset_id)
        return _row_to_out(row)

    async def create(self, project_id: str, data: SheetPresetCreate) -> SheetPresetOut:
        now = datetime.now(UTC)
        row = SheetPresetRow(
            id=uuid.uuid4().hex,
            project_id=project_id,
            name=data.name,
            field_defs=[f.model_dump(mode="json") for f in data.field_defs],
            section=data.section.model_dump(mode="json"),
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.commit()
        return _row_to_out(row)

    async def delete(self, preset_id: str) -> None:
        row = await self._session.get(SheetPresetRow, preset_id)
        if row is None:
            raise SheetPresetNotFoundError(preset_id)
        await self._session.delete(row)
        await self._session.commit()


def _row_to_out(row: SheetPresetRow) -> SheetPresetOut:
    return SheetPresetOut(
        id=row.id,
        project_id=row.project_id,
        is_builtin=False,
        name=row.name,
        field_defs=[TemplateFieldDef.model_validate(f) for f in row.field_defs],
        section=Section.model_validate(row.section),
    )
