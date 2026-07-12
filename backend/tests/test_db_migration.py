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
