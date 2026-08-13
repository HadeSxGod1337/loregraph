"""Rebuilding every vector collection after the embedding model changed.

Switching embedding models drops the old collections (they are not
comparable), so without this the assistant would silently retrieve nothing
until each project was reindexed by hand. One job at a time, for the whole
installation: it rewrites collections, and two of those racing would leave a
half-built index behind.

Both contours are rebuilt from their own source of truth — entities from
SQLite, knowledge-base chunks from the stored source files — so no state is
lost, only recomputed.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from loregraph.exceptions import ReindexInProgressError
from loregraph.services.embedding_stack import EmbeddingStack
from loregraph.services.knowledge_index import KnowledgeIndex
from loregraph.services.knowledge_ingest import ingest_source
from loregraph.storage.composition import StoreFactories

logger = logging.getLogger(__name__)

type ReindexState = Literal["idle", "running", "done", "error"]

# Truncated for the same reason knowledge ingest truncates its error: this
# string is surfaced in the UI and stored in memory, not a place for a
# full traceback.
REINDEX_ERROR_MAX_CHARS = 500


@dataclass
class ReindexProgress:
    """What the settings page polls while a reindex runs."""

    state: ReindexState = "idle"
    total_projects: int = 0
    done_projects: int = 0
    current_project: str | None = None
    # Reference documents are the slow part — a single 100 MB rulebook can
    # take longer than every entity in the installation put together — so
    # progress ticks per document, not per project.
    current_source: str | None = None
    total_sources: int = 0
    entities_indexed: int = 0
    sources_indexed: int = 0
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    # Which model the last completed run indexed with — lets the UI say
    # "indexed with X, now configured for Y" instead of guessing.
    model_id: str | None = None


class ReindexService:
    """Runs at most one full reindex, in the background, over all projects."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        store_factories: StoreFactories,
        stack: EmbeddingStack,
    ) -> None:
        self._session_factory = session_factory
        self._store_factories = store_factories
        self._stack = stack
        self._progress = ReindexProgress()
        self._task: asyncio.Task[None] | None = None

    @property
    def progress(self) -> ReindexProgress:
        return self._progress

    @property
    def is_running(self) -> bool:
        return self._progress.state == "running"

    def start(self) -> ReindexProgress:
        """Kick off a reindex and return immediately with its initial state."""
        if self.is_running:
            raise ReindexInProgressError()
        self._progress = ReindexProgress(
            state="running",
            started_at=datetime.now(UTC),
            model_id=self._stack.model_id,
        )
        self._task = asyncio.create_task(self._run())
        return self._progress

    async def stop(self) -> None:
        """Cancel a running job — called on shutdown, not from the API."""
        task = self._task
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            # Shutdown path: this task's cancellation is the expected outcome,
            # and we are not inside the cancelled task ourselves.
            pass

    async def _run(self) -> None:
        try:
            await self._reindex_all()
        except asyncio.CancelledError:
            self._progress.state = "idle"
            self._progress.finished_at = datetime.now(UTC)
            raise
        except Exception as e:
            logger.error("Reindex failed", exc_info=True)
            self._progress.state = "error"
            self._progress.error = str(e)[:REINDEX_ERROR_MAX_CHARS]
            self._progress.finished_at = datetime.now(UTC)
        else:
            self._progress.state = "done"
            self._progress.finished_at = datetime.now(UTC)

    async def _reindex_all(self) -> None:
        vector_index = self._stack.vector_index
        knowledge_index = self._stack.knowledge_index
        if vector_index is None:
            # Embeddings disabled: nothing to rebuild, and saying so beats
            # leaving the UI waiting on a job that will never report progress.
            logger.info("Reindex skipped: embeddings are disabled")
            return

        async with self._session_factory() as session:
            projects = await self._store_factories.project(session).list_projects()
            self._progress.total_projects = len(projects)
            if knowledge_index is not None:
                source_store = self._store_factories.knowledge_source(session)
                for project in projects:
                    sources = await source_store.list_for_project(project.id)
                    self._progress.total_sources += len(sources)

        for project in projects:
            self._progress.current_project = project.name
            async with self._session_factory() as session:
                entity_store = self._store_factories.entity(session)
                indexed = await vector_index.reindex_project(entity_store, project.id)
                self._progress.entities_indexed += indexed
                if knowledge_index is not None:
                    await self._reindex_knowledge(session, knowledge_index, project.id)
            self._progress.done_projects += 1
        self._progress.current_project = None
        self._progress.current_source = None
        self._progress.model_id = self._stack.model_id

    async def _reindex_knowledge(
        self, session: AsyncSession, knowledge_index: KnowledgeIndex, project_id: str
    ) -> None:
        """Re-embed the project's reference documents from the stored files.

        Dropping the collection first is what makes this a rebuild rather than
        an overwrite: a document that now chunks into fewer pieces than before
        would otherwise leave its tail chunks behind as orphans.
        """
        source_store = self._store_factories.knowledge_source(session)
        sources = await source_store.list_for_project(project_id)
        if not sources:
            return
        await knowledge_index.drop_project(project_id)
        for source in sources:
            self._progress.current_source = source.original_filename
            content = await source_store.read_content(source.id)
            # Same pipeline as a fresh upload (extract -> chunk -> index -> mark
            # ready), so a reindexed source ends up byte-identical to a
            # re-uploaded one, status transitions included.
            await ingest_source(
                source.id,
                project_id,
                content,
                source.content_type,
                source.original_filename,
                source_store=source_store,
                knowledge_index=knowledge_index,
            )
            self._progress.sources_indexed += 1
        self._progress.current_source = None
