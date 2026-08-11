from pathlib import Path

import pytest
from sqlalchemy import text

from loregraph.schemas.project import ProjectCreate
from loregraph.storage.sqlite.db import create_engine_for, init_db, make_session_factory
from loregraph.storage.sqlite.project_store import SqliteProjectStore


@pytest.mark.asyncio
async def test_init_db_backfills_missing_column_on_existing_database(
    tmp_path: Path,
) -> None:
    """Regression: create_all only creates missing TABLES. A `projects` table
    from before `agent_instructions` existed must still get the column added
    by init_db's migration pass, not crash or silently stay stale."""
    engine = create_engine_for(tmp_path / "old.sqlite3")
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE projects ("
                "id VARCHAR NOT NULL PRIMARY KEY, "
                "name VARCHAR NOT NULL, "
                "description VARCHAR, "
                "created_at DATETIME NOT NULL, "
                "updated_at DATETIME NOT NULL)"
            )
        )

    await init_db(engine)

    session = make_session_factory(engine)()
    try:
        store = SqliteProjectStore(session)
        project = await store.create(
            ProjectCreate(name="Old DB", agent_instructions="Be concise.")
        )
        assert project.agent_instructions == "Be concise."
        fetched = await store.get(project.id)
        assert fetched.agent_instructions == "Be concise."
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_init_db_is_idempotent(tmp_path: Path) -> None:
    engine = create_engine_for(tmp_path / "fresh.sqlite3")
    await init_db(engine)
    await init_db(engine)  # second pass must not error on already-present columns
    await engine.dispose()


@pytest.mark.asyncio
async def test_init_db_backfills_player_view_columns(tmp_path: Path) -> None:
    """An entities table from before limited player access must gain the
    revealed_to_players / player_text columns, and old rows must read back as
    "not revealed" (NULL), never crash."""
    from loregraph.storage.sqlite.entity_store import SqliteEntityStore

    engine = create_engine_for(tmp_path / "old.sqlite3")
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE projects (id VARCHAR PRIMARY KEY)"))
        await conn.execute(
            text(
                "CREATE TABLE entities ("
                "id VARCHAR NOT NULL PRIMARY KEY, "
                "project_id VARCHAR NOT NULL, "
                "type VARCHAR NOT NULL, "
                "title VARCHAR NOT NULL, "
                "fields JSON, "
                "created_at DATETIME NOT NULL, "
                "updated_at DATETIME NOT NULL)"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO entities "
                "(id, project_id, type, title, fields, created_at, updated_at) "
                "VALUES ('e1', 'p1', 'npc', 'Old', '[]', "
                "'2020-01-01', '2020-01-01')"
            )
        )

    await init_db(engine)

    session = make_session_factory(engine)()
    try:
        entity = await SqliteEntityStore(session).get("e1")
        assert entity.revealed_to_players is False
        assert entity.player_text is None
    finally:
        await session.close()
        await engine.dispose()
