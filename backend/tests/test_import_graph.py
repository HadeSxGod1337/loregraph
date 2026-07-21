"""Smoke/integration tests for the bulk-import subgraph (agent/import_graph.py):
proves the graph wiring itself — fan-out really runs concurrently, the
single interrupt lands after every parallel phase has joined, approve/
reject/approve_all drive the right commit sequence, and everything
resumes correctly via a real (not in-memory) checkpointer. Merge/dedup
logic itself (the trickiest part) has its own focused unit tests in
test_import_merge.py — this file only needs uniform fake responses."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.agent.import_graph import build_import_graph
from loregraph.agent.import_source import ImportSourceResolver
from loregraph.agent.import_state import ImportState
from loregraph.connectors.protocols import IngestSource
from loregraph.llm.structured import StructuredResult
from loregraph.llm.usage import LLMCallUsage
from loregraph.schemas.agent import DraftEntity, DraftRelationship, LoreDraft
from loregraph.schemas.import_job import RegistryEntryDraft, WindowRegistryDraft
from loregraph.schemas.project import ProjectCreate
from loregraph.services.edge_service import EdgeService
from loregraph.services.entity_service import EntityService
from loregraph.storage.sqlite.db import create_engine_for, init_db, make_session_factory
from loregraph.storage.sqlite.edge_store import SqliteEdgeStore
from loregraph.storage.sqlite.entity_store import SqliteEntityStore
from loregraph.storage.sqlite.knowledge_source_store import SqliteKnowledgeSourceStore
from loregraph.storage.sqlite.project_store import SqliteProjectStore


def _resolver(source_store: SqliteKnowledgeSourceStore) -> ImportSourceResolver:
    """File-import path only — these tests never migrate from a connection,
    so the connection factory must never be reached."""

    async def _no_connections(project_id: str, connection_id: str) -> IngestSource:
        raise AssertionError("file-import tests must not resolve a connection")

    return ImportSourceResolver(source_store, _no_connections)


class ConcurrencyTrackingGenerator:
    """Returns a canned result per schema type; also records how many calls
    were in flight at once, to prove the fan-out is real concurrency, not
    accidental serialization."""

    def __init__(
        self, registry_draft: WindowRegistryDraft, lore_draft: LoreDraft
    ) -> None:
        self._registry_draft = registry_draft
        self._lore_draft = lore_draft
        self.in_flight = 0
        self.max_in_flight = 0

    async def generate[T: BaseModel](
        self, schema: type[T], *, system: str, user: str, cached_prefix: str = ""
    ) -> StructuredResult[T]:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0.01)  # give concurrent calls a chance to overlap
        value = (
            self._registry_draft if schema is WindowRegistryDraft else self._lore_draft
        )
        assert isinstance(value, schema)
        self.in_flight -= 1
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


def _long_text(paragraphs: int) -> str:
    # Long enough to split into multiple ~20k-char windows so the fan-out
    # actually has more than one task to run concurrently.
    return "\n\n".join(f"Параграф номер {i}. " * 900 for i in range(paragraphs))


@pytest.mark.asyncio
async def test_import_graph_fans_out_concurrently_and_interrupts_once(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    source_store = SqliteKnowledgeSourceStore(db_session, tmp_path / "knowledge")
    text = _long_text(6)
    source = await source_store.create(
        project_id=project.id,
        original_filename="lore.txt",
        content_type="text/plain",
        content=text.encode("utf-8"),
    )

    entity_store = SqliteEntityStore(db_session)
    edge_store = SqliteEdgeStore(db_session)
    generator = ConcurrencyTrackingGenerator(
        registry_draft=WindowRegistryDraft(
            entries=[RegistryEntryDraft(canonical_name="Шарп", type="npc")]
        ),
        lore_draft=LoreDraft(
            entities=[
                DraftEntity(ref="e1", type="npc", title="Шарп", summary="Кузнец."),
            ],
            relationships=[],
        ),
    )
    graph = build_import_graph(
        extraction=generator,
        creative=generator,
        source_resolver=_resolver(source_store),
        entity_store=entity_store,
        entity_service=EntityService(entity_store),
        edge_service=EdgeService(edge_store, entity_store),
        checkpointer=MemorySaver(),
    )
    config: RunnableConfig = {"configurable": {"thread_id": "job-1"}}

    await graph.ainvoke(  # type: ignore[call-overload]
        {
            "project_id": project.id,
            "source_id": source.id,
            "source_filename": source.original_filename,
        },
        config,
    )

    assert generator.max_in_flight > 1, (
        "windows must run concurrently, not one at a time"
    )

    snapshot = await graph.aget_state(config)
    assert any(task.interrupts for task in snapshot.tasks)
    state = ImportState.model_validate(snapshot.values)
    assert len(state.windows) > 1
    # Every window named the same person ("Шарп") — merge must have
    # collapsed them into ONE entity, not one per window.
    assert len(state.merged_entities) == 1
    assert state.review_slices[0].entities[0].title == "Шарп"


@pytest.mark.asyncio
async def test_approve_commits_entities_and_relationships(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    source_store = SqliteKnowledgeSourceStore(db_session, tmp_path / "knowledge")
    source = await source_store.create(
        project_id=project.id,
        original_filename="lore.txt",
        content_type="text/plain",
        content="Шарп — кузнец. Он служит гильдии Ковка.".encode(),
    )
    entity_store = SqliteEntityStore(db_session)
    edge_store = SqliteEdgeStore(db_session)
    generator = ConcurrencyTrackingGenerator(
        registry_draft=WindowRegistryDraft(entries=[]),
        lore_draft=LoreDraft(
            entities=[
                DraftEntity(ref="e1", type="npc", title="Шарп", summary="Кузнец."),
                DraftEntity(
                    ref="e2", type="faction", title="Гильдия Ковка", summary="Цех."
                ),
            ],
            relationships=[
                DraftRelationship(
                    source_ref="e1", target_ref="e2", type="member_of", reason="служит"
                ),
            ],
        ),
    )
    graph = build_import_graph(
        extraction=generator,
        creative=generator,
        source_resolver=_resolver(source_store),
        entity_store=entity_store,
        entity_service=EntityService(entity_store),
        edge_service=EdgeService(edge_store, entity_store),
        checkpointer=MemorySaver(),
    )
    config: RunnableConfig = {"configurable": {"thread_id": "job-2"}}
    await graph.ainvoke(  # type: ignore[call-overload]
        {
            "project_id": project.id,
            "source_id": source.id,
            "source_filename": source.original_filename,
        },
        config,
    )

    await graph.ainvoke(Command(resume={"action": "approve"}), config)

    entities = await entity_store.list_entities(project.id)
    assert {e.title for e in entities} == {"Шарп", "Гильдия Ковка"}
    edges = await edge_store.list_all(project.id)
    assert [e.type for e in edges] == ["member_of"]

    state = ImportState.model_validate((await graph.aget_state(config)).values)
    assert len(state.committed_entity_ids) == 2
    snapshot = await graph.aget_state(config)
    assert not snapshot.next  # job actually finished


@pytest.mark.asyncio
async def test_reject_skips_page_without_committing_it(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    source_store = SqliteKnowledgeSourceStore(db_session, tmp_path / "knowledge")
    source = await source_store.create(
        project_id=project.id,
        original_filename="lore.txt",
        content_type="text/plain",
        content=b"Some tiny lore text.",
    )
    entity_store = SqliteEntityStore(db_session)
    edge_store = SqliteEdgeStore(db_session)
    generator = ConcurrencyTrackingGenerator(
        registry_draft=WindowRegistryDraft(entries=[]),
        lore_draft=LoreDraft(
            entities=[DraftEntity(ref="e1", type="npc", title="Кто-то", summary="...")],
            relationships=[],
        ),
    )
    graph = build_import_graph(
        extraction=generator,
        creative=generator,
        source_resolver=_resolver(source_store),
        entity_store=entity_store,
        entity_service=EntityService(entity_store),
        edge_service=EdgeService(edge_store, entity_store),
        checkpointer=MemorySaver(),
    )
    config: RunnableConfig = {"configurable": {"thread_id": "job-3"}}
    await graph.ainvoke(  # type: ignore[call-overload]
        {
            "project_id": project.id,
            "source_id": source.id,
            "source_filename": source.original_filename,
        },
        config,
    )

    await graph.ainvoke(Command(resume={"action": "reject"}), config)

    entities = await entity_store.list_entities(project.id)
    assert entities == []
    state = ImportState.model_validate((await graph.aget_state(config)).values)
    assert state.committed_entity_ids == []
    snapshot = await graph.aget_state(config)
    assert not snapshot.next


@pytest.mark.asyncio
async def test_approve_all_commits_every_remaining_page_without_further_interrupts(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    source_store = SqliteKnowledgeSourceStore(db_session, tmp_path / "knowledge")
    # Many distinctly-named entities in one window's fake draft so pagination
    # (REVIEW_SLICE_SIZE) produces more than one page.
    from loregraph.agent.nodes.import_review import REVIEW_SLICE_SIZE

    entity_count = REVIEW_SLICE_SIZE + 3
    source = await source_store.create(
        project_id=project.id,
        original_filename="lore.txt",
        content_type="text/plain",
        content=b"Lore with many named entities.",
    )
    entity_store = SqliteEntityStore(db_session)
    edge_store = SqliteEdgeStore(db_session)
    # Distinct-enough titles: short numeric-suffixed labels like "NPC 0"/
    # "NPC 17" are pathological for fuzzy-ratio matching (high edit-distance
    # similarity despite being different entities) — real lore titles don't
    # share a common prefix+short-suffix shape like that, so this generates
    # names that don't accidentally collide under FUZZY_MERGE_RATIO.
    names = [
        "Норвинтер",
        "Мира Кузнец",
        "Гильдия Ковка",
        "Торвальд Молот",
        "Аренлот",
        "Крепость Ветров",
        "Синдикат Соли",
        "Барон Освальд",
        "Долина Пепла",
        "Орден Стражей",
        "Капитан Ирвин",
        "Рынок Теней",
        "Маяк Севера",
        "Клан Волка",
        "Хранитель Лир",
        "Порт Гримвальд",
        "Совет Старейшин",
        "Библиотека Эха",
    ][:entity_count]
    assert len(names) == entity_count
    generator = ConcurrencyTrackingGenerator(
        registry_draft=WindowRegistryDraft(entries=[]),
        lore_draft=LoreDraft(
            entities=[
                DraftEntity(ref=f"e{i}", type="npc", title=name, summary="...")
                for i, name in enumerate(names)
            ],
            relationships=[],
        ),
    )
    graph = build_import_graph(
        extraction=generator,
        creative=generator,
        source_resolver=_resolver(source_store),
        entity_store=entity_store,
        entity_service=EntityService(entity_store),
        edge_service=EdgeService(edge_store, entity_store),
        checkpointer=MemorySaver(),
    )
    config: RunnableConfig = {"configurable": {"thread_id": "job-4"}}
    await graph.ainvoke(  # type: ignore[call-overload]
        {
            "project_id": project.id,
            "source_id": source.id,
            "source_filename": source.original_filename,
        },
        config,
    )
    state_before = ImportState.model_validate((await graph.aget_state(config)).values)
    assert state_before.review_slices and len(state_before.review_slices) > 1

    await graph.ainvoke(Command(resume={"action": "approve_all"}), config)

    entities = await entity_store.list_entities(project.id)
    assert len(entities) == entity_count
    snapshot = await graph.aget_state(config)
    assert not snapshot.next  # finished without any further interrupt


@pytest.mark.asyncio
async def test_import_job_resumes_after_a_real_checkpointer_restart(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """Not MemorySaver: a real AsyncSqliteSaver on disk, graph object
    discarded and rebuilt, to prove the interrupted job survives a process
    restart exactly like the main chat graph does."""
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    source_store = SqliteKnowledgeSourceStore(db_session, tmp_path / "knowledge")
    source = await source_store.create(
        project_id=project.id,
        original_filename="lore.txt",
        content_type="text/plain",
        content=b"Small lore text.",
    )
    entity_store = SqliteEntityStore(db_session)
    edge_store = SqliteEdgeStore(db_session)
    generator = ConcurrencyTrackingGenerator(
        registry_draft=WindowRegistryDraft(entries=[]),
        lore_draft=LoreDraft(
            entities=[DraftEntity(ref="e1", type="npc", title="Один", summary="...")],
            relationships=[],
        ),
    )
    config: RunnableConfig = {"configurable": {"thread_id": "job-5"}}
    db_path = tmp_path / "import_checkpoints.sqlite3"

    async with AsyncSqliteSaver.from_conn_string(str(db_path)) as checkpointer:
        graph = build_import_graph(
            extraction=generator,
            creative=generator,
            source_resolver=_resolver(source_store),
            entity_store=entity_store,
            entity_service=EntityService(entity_store),
            edge_service=EdgeService(edge_store, entity_store),
            checkpointer=checkpointer,
        )
        await graph.ainvoke(  # type: ignore[call-overload]
            {
                "project_id": project.id,
                "source_id": source.id,
                "source_filename": source.original_filename,
            },
            config,
        )

    # Simulate a process restart: brand-new checkpointer + graph object
    # against the same on-disk file.
    async with AsyncSqliteSaver.from_conn_string(str(db_path)) as checkpointer2:
        graph2 = build_import_graph(
            extraction=generator,
            creative=generator,
            source_resolver=_resolver(source_store),
            entity_store=entity_store,
            entity_service=EntityService(entity_store),
            edge_service=EdgeService(edge_store, entity_store),
            checkpointer=checkpointer2,
        )
        snapshot = await graph2.aget_state(config)
        assert any(task.interrupts for task in snapshot.tasks)
        await graph2.ainvoke(Command(resume={"action": "approve"}), config)

    entities = await entity_store.list_entities(project.id)
    assert [e.title for e in entities] == ["Один"]
