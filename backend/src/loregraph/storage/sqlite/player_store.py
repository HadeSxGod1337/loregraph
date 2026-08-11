import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.exceptions import PlayerNotFoundError
from loregraph.schemas.player import PlayerOut
from loregraph.storage.sqlite.models import PlayerRow


class SqlitePlayerStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_project(self, project_id: str) -> list[PlayerOut]:
        rows = (
            (
                await self._session.execute(
                    select(PlayerRow)
                    .where(PlayerRow.project_id == project_id)
                    .order_by(PlayerRow.created_at)
                )
            )
            .scalars()
            .all()
        )
        return [_row_to_out(row) for row in rows]

    async def get(self, player_id: str) -> PlayerOut:
        return _row_to_out(await self._require(player_id))

    async def create(
        self, project_id: str, name: str, token_hash: str, token_prefix: str
    ) -> PlayerOut:
        now = datetime.now(UTC)
        row = PlayerRow(
            id=uuid.uuid4().hex,
            project_id=project_id,
            name=name,
            token_hash=token_hash,
            token_prefix=token_prefix,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.commit()
        return _row_to_out(row)

    async def rename(self, player_id: str, name: str) -> PlayerOut:
        row = await self._require(player_id)
        row.name = name
        row.updated_at = datetime.now(UTC)
        await self._session.commit()
        return _row_to_out(row)

    async def set_token(
        self, player_id: str, token_hash: str, token_prefix: str
    ) -> PlayerOut:
        row = await self._require(player_id)
        row.token_hash = token_hash
        row.token_prefix = token_prefix
        # Rotating a token reactivates a revoked player: the new link works.
        row.revoked_at = None
        row.updated_at = datetime.now(UTC)
        await self._session.commit()
        return _row_to_out(row)

    async def set_revoked(self, player_id: str, revoked: bool) -> PlayerOut:
        row = await self._require(player_id)
        row.revoked_at = datetime.now(UTC) if revoked else None
        row.updated_at = datetime.now(UTC)
        await self._session.commit()
        return _row_to_out(row)

    async def delete(self, player_id: str) -> None:
        row = await self._require(player_id)
        await self._session.delete(row)
        await self._session.commit()

    async def find_active_by_token_hash(self, token_hash: str) -> PlayerOut | None:
        row = (
            await self._session.execute(
                select(PlayerRow).where(PlayerRow.token_hash == token_hash)
            )
        ).scalar_one_or_none()
        if row is None or row.revoked_at is not None:
            return None
        return _row_to_out(row)

    async def touch_last_seen(self, player_id: str) -> None:
        row = await self._session.get(PlayerRow, player_id)
        if row is None:
            return
        row.last_seen_at = datetime.now(UTC)
        await self._session.commit()

    async def _require(self, player_id: str) -> PlayerRow:
        row = await self._session.get(PlayerRow, player_id)
        if row is None:
            raise PlayerNotFoundError(player_id)
        return row


def _row_to_out(row: PlayerRow) -> PlayerOut:
    return PlayerOut(
        id=row.id,
        project_id=row.project_id,
        name=row.name,
        token_prefix=row.token_prefix,
        revoked=row.revoked_at is not None,
        last_seen_at=row.last_seen_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
