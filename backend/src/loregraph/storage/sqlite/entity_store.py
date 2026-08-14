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
    EntityFieldIn,
    EntityFieldOut,
    EntityOut,
    EntityPatch,
    EntityPlayerViewUpdate,
    EntityPositionEntry,
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

    async def list_entity_types(self, project_id: str) -> list[str]:
        """The project's type vocabulary, without loading a single entity —
        every generation run needs it (to keep the model on one taxonomy) and
        the rows it would otherwise pull carry every rich-text field in the
        campaign."""
        stmt = (
            select(EntityRow.type)
            .where(EntityRow.project_id == project_id)
            .distinct()
            .order_by(EntityRow.type)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def create(self, data: EntityCreate, project_id: str) -> EntityOut:
        now = datetime.now(UTC)
        row = EntityRow(
            id=uuid.uuid4().hex,
            project_id=project_id,
            type=data.type,
            title=data.title,
            fields=[f.model_dump(mode="json") for f in data.fields],
            template_id=data.template_id,
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
        row.template_id = data.template_id
        row.updated_at = datetime.now(UTC)
        await self._session.commit()
        return _row_to_out(row)

    async def patch(self, entity_id: str, data: EntityPatch) -> EntityOut:
        """Partial update: everything the patch doesn't name survives.

        Unlike `update`, which rewrites the row from what the caller supplies,
        this touches only the named keys — so `template_id`, attachment
        fields, and the per-field `show_on_card` / `visible_to_players` flags
        cannot be erased by a caller that never saw them (see
        schemas/entity.py::EntityPatch).
        """
        row = await self._session.get(EntityRow, entity_id)
        if row is None:
            raise EntityNotFoundError(entity_id)

        current = [EntityFieldIn.model_validate(f) for f in row.fields]
        by_key = {field.key: field for field in current}
        order = [field.key for field in current]

        for incoming in data.set_fields:
            existing = by_key.get(incoming.key)
            if existing is None:
                order.append(incoming.key)
                by_key[incoming.key] = incoming
            else:
                # Value and type come from the patch; the visibility flags
                # stay with the entity. A caller editing prose has no opinion
                # about whether the field shows on the card or is revealed to
                # players, and defaulting them to False would quietly undo the
                # game master's own choices on every agent edit.
                by_key[incoming.key] = incoming.model_copy(
                    update={
                        "show_on_card": existing.show_on_card,
                        "visible_to_players": existing.visible_to_players,
                    }
                )

        removed = set(data.remove_field_keys)
        row.fields = [
            by_key[key].model_dump(mode="json")
            for key in dict.fromkeys(order)
            if key not in removed
        ]
        if data.type is not None:
            row.type = data.type
        if data.title is not None:
            row.title = data.title
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

    async def set_player_view(
        self, entity_id: str, data: EntityPlayerViewUpdate
    ) -> EntityOut:
        row = await self._session.get(EntityRow, entity_id)
        if row is None:
            raise EntityNotFoundError(entity_id)
        row.revealed_to_players = data.revealed_to_players
        row.player_text = data.player_text
        # The whitelist lives inside each field's JSON, so flip visible_to_players
        # per field to match the requested key set. A new list is assigned (not
        # mutated in place) so SQLAlchemy sees the JSON column as dirty.
        visible = set(data.visible_field_keys)
        row.fields = [
            {**field, "visible_to_players": field.get("key") in visible}
            for field in row.fields
        ]
        row.updated_at = datetime.now(UTC)
        await self._session.commit()
        return _row_to_out(row)

    async def update_positions(
        self, positions: Sequence[EntityPositionEntry]
    ) -> list[EntityOut]:
        # One commit for the whole batch, not one per row — drag-end saves a
        # single node, but "Reset Layout" can touch every node in view.
        rows: list[EntityRow] = []
        for entry in positions:
            row = await self._session.get(EntityRow, entry.entity_id)
            if row is None:
                raise EntityNotFoundError(entry.entity_id)
            row.pos_x = entry.pos_x
            row.pos_y = entry.pos_y
            rows.append(row)
        await self._session.commit()
        return [_row_to_out(row) for row in rows]


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
        template_id=row.template_id,
        icon=icon,
        pos_x=row.pos_x,
        pos_y=row.pos_y,
        revealed_to_players=bool(row.revealed_to_players),
        player_text=row.player_text,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
