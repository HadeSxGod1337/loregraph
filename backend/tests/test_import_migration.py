"""The migration seam: a connection's IngestSource feeding the SAME bulk
pipeline the file import uses (agent/import_source.py, import_plan.py), plus
the provenance marker migrated entities carry."""

from pathlib import Path
from typing import Any, cast

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.agent.import_source import ImportSourceResolver
from loregraph.agent.import_state import ImportState
from loregraph.agent.nodes.import_commit import commit_slice
from loregraph.agent.nodes.import_plan import plan_windows
from loregraph.connectors.protocols import IngestDocument, IngestSource
from loregraph.schemas.agent import DraftEntity, LoreDraft
from loregraph.schemas.project import ProjectCreate
from loregraph.services.entity_service import EntityService
from loregraph.storage.sqlite.db import create_engine_for, init_db, make_session_factory
from loregraph.storage.sqlite.entity_store import SqliteEntityStore
from loregraph.storage.sqlite.project_store import SqliteProjectStore


class FakeIngestSource:
    def __init__(self, documents: list[IngestDocument]) -> None:
        self.documents = documents

    async def ingest_documents(self) -> list[IngestDocument]:
        return self.documents


def _resolver(source: FakeIngestSource) -> ImportSourceResolver:
    async def factory(project_id: str, connection_id: str) -> IngestSource:
        return cast(IngestSource, source)

    return ImportSourceResolver(cast(Any, None), factory)


def _doc(title: str, text: str) -> IngestDocument:
    return IngestDocument(
        external_id=f"ext-{title}", title=title, text=text, kind="note"
    )


@pytest_asyncio.fixture
async def db_session(tmp_path: Path) -> Any:
    engine = create_engine_for(tmp_path / "test.sqlite3")
    await init_db(engine)
    session = make_session_factory(engine)()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_plan_windows_reads_a_connection_and_labels_each_document() -> None:
    """Connection sources are concatenated under `# title` headers so the
    extractor still sees each document's boundary, while short notes share
    windows instead of costing one extraction call each."""
    source = FakeIngestSource(
        [_doc("Strahd", "Lord of Barovia."), _doc("Ireena", "Sworn enemy of Strahd.")]
    )
    state = ImportState(
        project_id="p1",
        source_kind="connection",
        source_id="conn-1",
        source_filename="My Vault",
    )

    update = await plan_windows(state, source_resolver=_resolver(source))

    windows = update["windows"]
    assert len(windows) == 1  # both notes packed into one window
    text = windows[0].text
    assert "# Strahd" in text and "# Ireena" in text
    assert "Lord of Barovia." in text


@pytest.mark.asyncio
async def test_plan_windows_drops_empty_documents() -> None:
    source = FakeIngestSource([_doc("Real", "Content."), _doc("Blank", "   ")])
    state = ImportState(
        project_id="p1",
        source_kind="connection",
        source_id="conn-1",
        source_filename="My Vault",
    )

    update = await plan_windows(state, source_resolver=_resolver(source))

    assert "# Blank" not in update["windows"][0].text


@pytest.mark.asyncio
async def test_migrated_entities_carry_a_provenance_marker(
    db_session: AsyncSession,
) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    entity_store = SqliteEntityStore(db_session)
    entity_service = EntityService(entity_store, cast(Any, None))
    state = ImportState(
        project_id=project.id,
        source_kind="connection",
        source_id="conn-1",
        source_filename="My Foundry",
        review_slices=[
            LoreDraft(
                entities=[
                    DraftEntity(ref="m1", type="npc", title="Strahd", summary="Lord.")
                ],
                relationships=[],
            )
        ],
    )

    await commit_slice(state, entity_service=entity_service)

    entities = await entity_store.list_entities(project.id)
    fields = {f.key: f.value for f in entities[0].fields}
    assert fields["source"] == "Migrated from My Foundry"


@pytest.mark.asyncio
async def test_file_imported_entities_have_no_migration_marker(
    db_session: AsyncSession,
) -> None:
    """Provenance is migration-specific — the file-import path must be
    untouched by it."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    entity_store = SqliteEntityStore(db_session)
    entity_service = EntityService(entity_store, cast(Any, None))
    state = ImportState(
        project_id=project.id,
        source_id="src-1",
        source_filename="lore.pdf",
        review_slices=[
            LoreDraft(
                entities=[
                    DraftEntity(ref="m1", type="npc", title="Strahd", summary="Lord.")
                ],
                relationships=[],
            )
        ],
    )

    await commit_slice(state, entity_service=entity_service)

    entities = await entity_store.list_entities(project.id)
    assert "source" not in {f.key for f in entities[0].fields}
