import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from loregraph.exceptions import PlayerNotFoundError
from loregraph.schemas.entity import EntityCreate
from loregraph.storage.sqlite.db import create_engine_for, init_db, make_session_factory
from loregraph.storage.sqlite.entity_store import SqliteEntityStore
from loregraph.storage.sqlite.models import ProjectRow
from loregraph.storage.sqlite.player_note_store import SqlitePlayerNoteStore
from loregraph.storage.sqlite.player_store import SqlitePlayerStore


async def _session_factory(tmp_path: Path) -> async_sessionmaker[AsyncSession]:
    engine = create_engine_for(tmp_path / "test.sqlite3")
    await init_db(engine)
    return make_session_factory(engine)


async def _make_project(factory: async_sessionmaker[AsyncSession]) -> str:
    project_id = uuid.uuid4().hex
    async with factory() as session:
        now = datetime.now(UTC)
        session.add(ProjectRow(id=project_id, name="P", created_at=now, updated_at=now))
        await session.commit()
    return project_id


@pytest.mark.asyncio
async def test_player_lifecycle(tmp_path: Path) -> None:
    session_factory = await _session_factory(tmp_path)
    project_id = await _make_project(session_factory)
    async with session_factory() as session:
        store = SqlitePlayerStore(session)
        created = await store.create(project_id, "Alice", "hash-a", "prefixaa")
        assert created.revoked is False
        assert created.token_prefix == "prefixaa"

        # Active lookup finds it; revoke makes it disappear from active lookup.
        active = await store.find_active_by_token_hash("hash-a")
        assert active is not None and active.id == created.id
        await store.set_revoked(created.id, True)
        assert await store.find_active_by_token_hash("hash-a") is None
        assert (await store.get(created.id)).revoked is True

        # Rotating the token reactivates and invalidates the old hash.
        await store.set_token(created.id, "hash-b", "prefixbb")
        assert await store.find_active_by_token_hash("hash-a") is None
        rotated = await store.find_active_by_token_hash("hash-b")
        assert rotated is not None and rotated.revoked is False

        await store.delete(created.id)
        with pytest.raises(PlayerNotFoundError):
            await store.get(created.id)


@pytest.mark.asyncio
async def test_deleting_player_cascades_notes(tmp_path: Path) -> None:
    session_factory = await _session_factory(tmp_path)
    project_id = await _make_project(session_factory)
    async with session_factory() as session:
        entity = await SqliteEntityStore(session).create(
            EntityCreate(type="npc", title="Guard"), project_id
        )
        players = SqlitePlayerStore(session)
        notes = SqlitePlayerNoteStore(session)
        player = await players.create(project_id, "Bob", "h", "pfx")
        doc: dict[str, object] = {"type": "doc", "content": []}
        await notes.create(project_id, player.id, entity.id, doc, is_public=True)

        record = (await notes.list_for_entity(entity.id))[0]
        assert record.author_name == "Bob"
        assert record.is_public is True
        assert await notes.count_by_player(project_id) == {player.id: 1}

        await players.delete(player.id)
        assert await notes.list_for_entity(entity.id) == []
