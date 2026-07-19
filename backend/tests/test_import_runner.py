import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.agent.import_graph import build_import_graph
from loregraph.agent.import_runner import ImportJobRunner
from loregraph.llm.structured import StructuredResult
from loregraph.llm.usage import LLMCallUsage
from loregraph.schemas.agent import DraftEntity, LoreDraft
from loregraph.schemas.import_job import ImportReviewDecision, WindowRegistryDraft
from loregraph.schemas.project import ProjectCreate
from loregraph.services.edge_service import EdgeService
from loregraph.services.entity_service import EntityService
from loregraph.storage.sqlite.db import create_engine_for, init_db, make_session_factory
from loregraph.storage.sqlite.edge_store import SqliteEdgeStore
from loregraph.storage.sqlite.entity_store import SqliteEntityStore
from loregraph.storage.sqlite.import_job_store import SqliteImportJobStore
from loregraph.storage.sqlite.knowledge_source_store import SqliteKnowledgeSourceStore
from loregraph.storage.sqlite.project_store import SqliteProjectStore


class FakeGenerator:
    def __init__(
        self, registry_draft: WindowRegistryDraft, lore_draft: LoreDraft
    ) -> None:
        self._registry_draft = registry_draft
        self._lore_draft = lore_draft

    async def generate[T: BaseModel](
        self, schema: type[T], *, system: str, user: str, cached_prefix: str = ""
    ) -> StructuredResult[T]:
        value = (
            self._registry_draft if schema is WindowRegistryDraft else self._lore_draft
        )
        assert isinstance(value, schema)
        return StructuredResult(value, LLMCallUsage(input_tokens=10, output_tokens=5))


@pytest_asyncio.fixture
async def db_session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    engine = create_engine_for(tmp_path / "test.sqlite3")
    await init_db(engine)
    session = make_session_factory(engine)()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_runner_start_then_approve_reaches_committed(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    source_store = SqliteKnowledgeSourceStore(db_session, tmp_path / "knowledge")
    source = await source_store.create(
        project_id=project.id,
        original_filename="lore.txt",
        content_type="text/plain",
        content=b"Shorpe is a blacksmith.",
    )
    entity_store = SqliteEntityStore(db_session)
    edge_store = SqliteEdgeStore(db_session)
    generator = FakeGenerator(
        registry_draft=WindowRegistryDraft(entries=[]),
        lore_draft=LoreDraft(
            entities=[DraftEntity(ref="e1", type="npc", title="Shorpe", summary="...")],
            relationships=[],
        ),
    )
    graph = build_import_graph(
        extraction=generator,
        creative=generator,
        source_store=source_store,
        entity_store=entity_store,
        entity_service=EntityService(entity_store),
        edge_service=EdgeService(edge_store, entity_store),
        checkpointer=MemorySaver(),
    )
    jobs = SqliteImportJobStore(db_session)
    job_id = uuid.uuid4().hex
    await jobs.create(project.id, job_id, source.id, source.original_filename)
    runner = ImportJobRunner(graph, jobs)

    start_events = [
        e
        async for e in runner.stream_start(
            project.id, job_id, source.id, source.original_filename
        )
    ]
    assert any(e["type"] == "review" for e in start_events)
    job = await runner.get_detail(job_id)
    assert job.status == "awaiting_review"
    assert job.review is not None
    assert job.review.draft.entities[0].title == "Shorpe"

    review_events = [
        e
        async for e in runner.stream_review(
            job_id, ImportReviewDecision(action="approve")
        )
    ]
    assert any(e["type"] == "done" for e in review_events)
    job = await runner.get_detail(job_id)
    assert job.status == "committed"
    assert len(job.committed_entity_ids) == 1

    entities = await entity_store.list_entities(project.id)
    assert [e.title for e in entities] == ["Shorpe"]


@pytest.mark.asyncio
async def test_runner_rejects_review_when_job_not_awaiting_review(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    source_store = SqliteKnowledgeSourceStore(db_session, tmp_path / "knowledge")
    source = await source_store.create(
        project_id=project.id,
        original_filename="lore.txt",
        content_type="text/plain",
        content=b"text",
    )
    entity_store = SqliteEntityStore(db_session)
    edge_store = SqliteEdgeStore(db_session)
    generator = FakeGenerator(
        registry_draft=WindowRegistryDraft(entries=[]),
        lore_draft=LoreDraft(entities=[], relationships=[]),
    )
    graph = build_import_graph(
        extraction=generator,
        creative=generator,
        source_store=source_store,
        entity_store=entity_store,
        entity_service=EntityService(entity_store),
        edge_service=EdgeService(edge_store, entity_store),
        checkpointer=MemorySaver(),
    )
    jobs = SqliteImportJobStore(db_session)
    job_id = uuid.uuid4().hex
    await jobs.create(project.id, job_id, source.id, source.original_filename)
    runner = ImportJobRunner(graph, jobs)

    events = [
        e
        async for e in runner.stream_review(
            job_id, ImportReviewDecision(action="approve")
        )
    ]
    assert events == [
        {
            "type": "error",
            "code": "not_awaiting_review",
            "detail": "Import job is not awaiting review.",
        }
    ]
