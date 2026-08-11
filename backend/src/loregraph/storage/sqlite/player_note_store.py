import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.exceptions import PlayerNoteNotFoundError
from loregraph.schemas.player import PlayerNoteRecord
from loregraph.storage.sqlite.models import PlayerNoteRow, PlayerRow


class SqlitePlayerNoteStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_entity(self, entity_id: str) -> list[PlayerNoteRecord]:
        rows = (
            await self._session.execute(
                select(PlayerNoteRow, PlayerRow.name)
                .join(PlayerRow, PlayerRow.id == PlayerNoteRow.player_id)
                .where(PlayerNoteRow.entity_id == entity_id)
                .order_by(PlayerNoteRow.created_at)
            )
        ).all()
        return [_row_to_record(row, author_name) for row, author_name in rows]

    async def get(self, note_id: str) -> PlayerNoteRecord:
        row = await self._require(note_id)
        author_name = await self._author_name(row.player_id)
        return _row_to_record(row, author_name)

    async def create(
        self,
        project_id: str,
        player_id: str,
        entity_id: str,
        body: dict[str, object],
        is_public: bool,
    ) -> PlayerNoteRecord:
        now = datetime.now(UTC)
        row = PlayerNoteRow(
            id=uuid.uuid4().hex,
            project_id=project_id,
            player_id=player_id,
            entity_id=entity_id,
            is_public=is_public,
            body=body,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.commit()
        return _row_to_record(row, await self._author_name(player_id))

    async def update(
        self, note_id: str, body: dict[str, object], is_public: bool
    ) -> PlayerNoteRecord:
        row = await self._require(note_id)
        row.body = body
        row.is_public = is_public
        row.updated_at = datetime.now(UTC)
        await self._session.commit()
        return _row_to_record(row, await self._author_name(row.player_id))

    async def delete(self, note_id: str) -> None:
        row = await self._require(note_id)
        await self._session.delete(row)
        await self._session.commit()

    async def count_by_player(self, project_id: str) -> dict[str, int]:
        result = await self._session.execute(
            select(PlayerNoteRow.player_id, func.count())
            .where(PlayerNoteRow.project_id == project_id)
            .group_by(PlayerNoteRow.player_id)
        )
        return {player_id: count for player_id, count in result.all()}

    async def _require(self, note_id: str) -> PlayerNoteRow:
        row = await self._session.get(PlayerNoteRow, note_id)
        if row is None:
            raise PlayerNoteNotFoundError(note_id)
        return row

    async def _author_name(self, player_id: str) -> str:
        name = (
            await self._session.execute(
                select(PlayerRow.name).where(PlayerRow.id == player_id)
            )
        ).scalar_one_or_none()
        return name or ""


def _row_to_record(row: PlayerNoteRow, author_name: str) -> PlayerNoteRecord:
    return PlayerNoteRecord(
        id=row.id,
        project_id=row.project_id,
        author_player_id=row.player_id,
        author_name=author_name,
        entity_id=row.entity_id,
        is_public=row.is_public,
        body=row.body,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
