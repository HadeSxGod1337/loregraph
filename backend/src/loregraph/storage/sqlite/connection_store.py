import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.exceptions import ConnectionNotFoundError
from loregraph.schemas.connection import (
    ConnectionCreate,
    ConnectionEntityLinkOut,
    ConnectionOut,
    ConnectionUpdate,
)
from loregraph.storage.sqlite.models import ConnectionEntityLinkRow, ConnectionRow


class SqliteConnectionStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_project(self, project_id: str) -> list[ConnectionOut]:
        stmt = select(ConnectionRow).where(ConnectionRow.project_id == project_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_row_to_out(row) for row in rows]

    async def create(self, project_id: str, data: ConnectionCreate) -> ConnectionOut:
        now = datetime.now(UTC)
        row = ConnectionRow(
            id=uuid.uuid4().hex,
            project_id=project_id,
            connector_type=data.connector_type,
            name=data.name,
            config_json=json.dumps(data.config),
            use_for_grounding=data.use_for_grounding,
            auto_push_after_commit=data.auto_push_after_commit,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.commit()
        return _row_to_out(row)

    async def get(self, connection_id: str) -> ConnectionOut:
        row = await self._session.get(ConnectionRow, connection_id)
        if row is None:
            raise ConnectionNotFoundError(connection_id)
        return _row_to_out(row)

    async def update(self, connection_id: str, data: ConnectionUpdate) -> ConnectionOut:
        row = await self._session.get(ConnectionRow, connection_id)
        if row is None:
            raise ConnectionNotFoundError(connection_id)
        row.name = data.name
        row.config_json = json.dumps(data.config)
        row.use_for_grounding = data.use_for_grounding
        row.auto_push_after_commit = data.auto_push_after_commit
        row.updated_at = datetime.now(UTC)
        await self._session.commit()
        return _row_to_out(row)

    async def delete(self, connection_id: str) -> None:
        row = await self._session.get(ConnectionRow, connection_id)
        if row is None:
            raise ConnectionNotFoundError(connection_id)
        await self._session.delete(row)
        await self._session.commit()


class SqliteConnectionEntityLinkStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        connection_id: str,
        entity_id: str,
        external_id: str,
        external_kind: str,
    ) -> ConnectionEntityLinkOut:
        # One link per (connection, entity, kind): an entity maps to at most
        # one external object of a given kind within one connection.
        stmt = select(ConnectionEntityLinkRow).where(
            ConnectionEntityLinkRow.connection_id == connection_id,
            ConnectionEntityLinkRow.entity_id == entity_id,
            ConnectionEntityLinkRow.external_kind == external_kind,
        )
        row = (await self._session.execute(stmt)).scalars().first()
        now = datetime.now(UTC)
        if row is None:
            row = ConnectionEntityLinkRow(
                id=uuid.uuid4().hex,
                connection_id=connection_id,
                entity_id=entity_id,
                external_id=external_id,
                external_kind=external_kind,
                last_synced_at=now,
            )
            self._session.add(row)
        else:
            row.external_id = external_id
            row.last_synced_at = now
        await self._session.commit()
        return _link_row_to_out(row)

    async def list_for_connection(
        self, connection_id: str
    ) -> list[ConnectionEntityLinkOut]:
        stmt = select(ConnectionEntityLinkRow).where(
            ConnectionEntityLinkRow.connection_id == connection_id
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_link_row_to_out(row) for row in rows]

    async def get_by_external(
        self, connection_id: str, external_kind: str, external_id: str
    ) -> ConnectionEntityLinkOut | None:
        stmt = select(ConnectionEntityLinkRow).where(
            ConnectionEntityLinkRow.connection_id == connection_id,
            ConnectionEntityLinkRow.external_kind == external_kind,
            ConnectionEntityLinkRow.external_id == external_id,
        )
        row = (await self._session.execute(stmt)).scalars().first()
        return _link_row_to_out(row) if row is not None else None

    async def list_for_entity(
        self, connection_id: str, entity_id: str
    ) -> list[ConnectionEntityLinkOut]:
        stmt = select(ConnectionEntityLinkRow).where(
            ConnectionEntityLinkRow.connection_id == connection_id,
            ConnectionEntityLinkRow.entity_id == entity_id,
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_link_row_to_out(row) for row in rows]

    async def delete_for_entity(self, connection_id: str, entity_id: str) -> None:
        stmt = select(ConnectionEntityLinkRow).where(
            ConnectionEntityLinkRow.connection_id == connection_id,
            ConnectionEntityLinkRow.entity_id == entity_id,
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        for row in rows:
            await self._session.delete(row)
        await self._session.commit()


def _row_to_out(row: ConnectionRow) -> ConnectionOut:
    return ConnectionOut(
        id=row.id,
        project_id=row.project_id,
        connector_type=row.connector_type,
        name=row.name,
        config=json.loads(row.config_json),
        use_for_grounding=row.use_for_grounding,
        auto_push_after_commit=row.auto_push_after_commit,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _link_row_to_out(row: ConnectionEntityLinkRow) -> ConnectionEntityLinkOut:
    return ConnectionEntityLinkOut(
        id=row.id,
        connection_id=row.connection_id,
        entity_id=row.entity_id,
        external_id=row.external_id,
        external_kind=row.external_kind,
        last_synced_at=row.last_synced_at,
    )
