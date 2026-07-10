import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.exceptions import (
    AttachmentNotFoundError,
    EntityNotFoundError,
    InvalidIconReferenceError,
)
from loregraph.schemas.entity import (
    AttachmentRef,
    EntityCreate,
    EntityFieldOut,
    EntityOut,
    EntityUpdate,
)
from loregraph.storage.sqlite.attachment_store import attachment_url
from loregraph.storage.sqlite.models import AttachmentRow, EntityRow


class SqliteEntityStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_entities(
        self, project_id: str, entity_type: str | None = None
    ) -> list[EntityOut]:
        stmt = select(EntityRow).where(EntityRow.project_id == project_id)
        if entity_type is not None:
            stmt = stmt.where(EntityRow.type == entity_type)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_row_to_out(row) for row in rows]

    async def create(self, data: EntityCreate, project_id: str) -> EntityOut:
        now = datetime.now(UTC)
        row = EntityRow(
            id=uuid.uuid4().hex,
            project_id=project_id,
            type=data.type,
            title=data.title,
            fields=[f.model_dump(mode="json") for f in data.fields],
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.commit()
        return _row_to_out(row)

    async def get(self, entity_id: str) -> EntityOut:
        row = await self._session.get(EntityRow, entity_id)
        if row is None:
            raise EntityNotFoundError(entity_id)
        return _row_to_out(row)

    async def get_many(self, entity_ids: Sequence[str]) -> list[EntityOut]:
        if not entity_ids:
            return []
        stmt = select(EntityRow).where(EntityRow.id.in_(entity_ids))
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_row_to_out(row) for row in rows]

    async def exists(self, entity_id: str) -> bool:
        return await self._session.get(EntityRow, entity_id) is not None

    async def update(self, entity_id: str, data: EntityUpdate) -> EntityOut:
        row = await self._session.get(EntityRow, entity_id)
        if row is None:
            raise EntityNotFoundError(entity_id)
        row.type = data.type
        row.title = data.title
        row.fields = [f.model_dump(mode="json") for f in data.fields]
        row.updated_at = datetime.now(UTC)
        await self._session.commit()
        return _row_to_out(row)

    async def delete(self, entity_id: str) -> None:
        row = await self._session.get(EntityRow, entity_id)
        if row is None:
            raise EntityNotFoundError(entity_id)
        await self._session.delete(row)
        await self._session.commit()

    async def set_icon(self, entity_id: str, attachment_id: str | None) -> EntityOut:
        row = await self._session.get(EntityRow, entity_id)
        if row is None:
            raise EntityNotFoundError(entity_id)
        if attachment_id is not None:
            attachment = await self._session.get(AttachmentRow, attachment_id)
            if attachment is None:
                raise AttachmentNotFoundError(attachment_id)
            if attachment.entity_id != entity_id:
                raise InvalidIconReferenceError(attachment_id)
        row.icon_attachment_id = attachment_id
        row.updated_at = datetime.now(UTC)
        await self._session.commit()
        # expire_on_commit=False means the eager-loaded `icon` relationship is
        # stale after mutating the FK column directly — refresh just that.
        await self._session.refresh(row, attribute_names=["icon"])
        return _row_to_out(row)


def _row_to_out(row: EntityRow) -> EntityOut:
    icon = (
        AttachmentRef(attachment_id=row.icon.id, url=attachment_url(row.icon))
        if row.icon is not None
        else None
    )
    return EntityOut(
        id=row.id,
        project_id=row.project_id,
        type=row.type,
        title=row.title,
        fields=[EntityFieldOut.model_validate(f) for f in row.fields],
        icon=icon,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
