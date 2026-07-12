from pathlib import Path

from sqlalchemy import event, inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from loregraph.storage.sqlite.models import Base


def create_engine_for(db_path: Path) -> AsyncEngine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_pragmas(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return engine


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


def _add_missing_columns(conn: Connection) -> None:
    """Idempotent additive-column migration for pre-existing SQLite files.

    create_all only creates missing TABLES, never missing COLUMNS on a table
    that already exists on disk from an older app version. This project has
    no Alembic (pre-1.0, single local sqlite file) — a small ALTER TABLE ADD
    COLUMN pass covers it, as long as new columns are always nullable so old
    rows don't need a backfill value.
    """
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())
    # .tables.values(), not .sorted_tables: adding columns to existing tables
    # has no cross-table ordering dependency, and this schema's entities<->
    # attachments FK cycle makes sorted_tables warn on every startup.
    for table in Base.metadata.tables.values():
        if table.name not in existing_tables:
            continue  # brand-new table — create_all already built it in full
        existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_columns:
                continue
            ddl_type = column.type.compile(dialect=conn.dialect)
            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl_type}'
            conn.execute(text(ddl))


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, expire_on_commit=False)
