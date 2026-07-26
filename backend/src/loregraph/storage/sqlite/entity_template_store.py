import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.exceptions import EntityTemplateNotFoundError
from loregraph.schemas.entity_template import (
    EntityTemplateCreate,
    EntityTemplateOut,
    EntityTemplateUpdate,
    ExternalEmbedDef,
    SheetLayout,
    TemplateFieldDef,
)
from loregraph.storage.sqlite.models import EntityTemplateRow


class SqliteEntityTemplateStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_project(self, project_id: str) -> list[EntityTemplateOut]:
        stmt = select(EntityTemplateRow).where(
            EntityTemplateRow.project_id == project_id
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_row_to_out(row) for row in rows]

    async def get(self, template_id: str) -> EntityTemplateOut:
        row = await self._session.get(EntityTemplateRow, template_id)
        if row is None:
            raise EntityTemplateNotFoundError(template_id)
        return _row_to_out(row)

    async def create(
        self, project_id: str, data: EntityTemplateCreate
    ) -> EntityTemplateOut:
        now = datetime.now(UTC)
        row = EntityTemplateRow(
            id=uuid.uuid4().hex,
            project_id=project_id,
            name=data.name,
            entity_type=data.entity_type,
            icon=data.icon,
            field_defs=[f.model_dump(mode="json") for f in data.field_defs],
            layout=data.layout.model_dump(mode="json"),
            external_embed=(
                data.external_embed.model_dump(mode="json")
                if data.external_embed is not None
                else None
            ),
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.commit()
        return _row_to_out(row)

    async def update(
        self, template_id: str, data: EntityTemplateUpdate
    ) -> EntityTemplateOut:
        row = await self._session.get(EntityTemplateRow, template_id)
        if row is None:
            raise EntityTemplateNotFoundError(template_id)
        row.name = data.name
        row.entity_type = data.entity_type
        row.icon = data.icon
        row.field_defs = [f.model_dump(mode="json") for f in data.field_defs]
        row.layout = data.layout.model_dump(mode="json")
        row.external_embed = (
            data.external_embed.model_dump(mode="json")
            if data.external_embed is not None
            else None
        )
        row.updated_at = datetime.now(UTC)
        await self._session.commit()
        return _row_to_out(row)

    async def delete(self, template_id: str) -> None:
        row = await self._session.get(EntityTemplateRow, template_id)
        if row is None:
            raise EntityTemplateNotFoundError(template_id)
        await self._session.delete(row)
        await self._session.commit()


def _row_to_out(row: EntityTemplateRow) -> EntityTemplateOut:
    return EntityTemplateOut(
        id=row.id,
        project_id=row.project_id,
        is_builtin=False,
        name=row.name,
        entity_type=row.entity_type,
        icon=row.icon,
        field_defs=[TemplateFieldDef.model_validate(f) for f in row.field_defs],
        layout=SheetLayout.model_validate(row.layout),
        external_embed=(
            ExternalEmbedDef.model_validate(row.external_embed)
            if row.external_embed is not None
            else None
        ),
    )
