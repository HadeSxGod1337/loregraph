"""The rebuild that has to follow an embedding-model change."""

import asyncio
from collections.abc import Sequence
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from loregraph.config import Settings
from loregraph.exceptions import ReindexInProgressError
from loregraph.llm.embeddings import EmbeddingProvider
from loregraph.services.embedding_stack import EmbeddingStack
from loregraph.services.reindex_job import ReindexService
from loregraph.storage.vectorstore.protocols import LoreChunk, RetrievedChunk

REINDEX_WAIT_TICKS = 500


class RecordingVectorStore:
    """Remembers what was written per collection, so a test can tell a
    rebuild from a no-op."""

    def __init__(self) -> None:
        self.upserted: dict[str, list[str]] = {}
        self.dropped: list[str] = []

    async def upsert(self, project_id: str, chunks: Sequence[LoreChunk]) -> None:
        self.upserted.setdefault(project_id, []).extend(
            chunk.entity_id for chunk in chunks
        )

    async def delete(self, project_id: str, entity_ids: Sequence[str]) -> None: ...

    async def query(
        self, project_id: str, text: str, k: int = 5
    ) -> list[RetrievedChunk]:
        return []

    async def drop_project(self, project_id: str) -> None:
        self.dropped.append(project_id)
        self.upserted.pop(project_id, None)


class FakeEmbedder:
    @property
    def model_id(self) -> str:
        return "fake-model"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0, 1.0] for _ in texts]


@pytest.fixture
def store() -> RecordingVectorStore:
    return RecordingVectorStore()


@pytest.fixture
def stack(settings: Settings, store: RecordingVectorStore) -> EmbeddingStack:
    def build_store(
        _settings: Settings, embedder: EmbeddingProvider | None
    ) -> RecordingVectorStore | None:
        return store if embedder is not None else None

    def build_embedder(_settings: Settings) -> EmbeddingProvider | None:
        return cast(EmbeddingProvider, FakeEmbedder())

    return EmbeddingStack(settings, build_store, build_embedder)


@pytest.fixture
def service(client: TestClient, app: FastAPI, stack: EmbeddingStack) -> ReindexService:
    # Depends on `client`: app.state is populated by the lifespan, which the
    # test client is what starts.
    return ReindexService(app.state.session_factory, app.state.store_factories, stack)


async def _run_to_completion(service: ReindexService) -> None:
    service.start()
    for _ in range(REINDEX_WAIT_TICKS):
        if not service.is_running:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("reindex did not finish in time")


@pytest.mark.asyncio
async def test_rebuilds_every_project_from_sqlite(
    client: TestClient,
    project_id: str,
    service: ReindexService,
    store: RecordingVectorStore,
) -> None:
    created = client.post(
        f"/api/projects/{project_id}/entities",
        json={"type": "npc", "title": "Мира Кузнец", "fields": []},
    )
    assert created.status_code == 201
    entity_id = created.json()["id"]

    await _run_to_completion(service)

    assert service.progress.state == "done"
    # SQLite is the source of truth: the collection is dropped and refilled
    # from it, so the entity is present with the new model's vectors.
    assert project_id in store.dropped
    assert store.upserted[project_id] == [entity_id]


@pytest.mark.asyncio
async def test_progress_counts_projects_and_entities(
    client: TestClient, project_id: str, service: ReindexService
) -> None:
    client.post(
        f"/api/projects/{project_id}/entities",
        json={"type": "npc", "title": "Страж", "fields": []},
    )

    await _run_to_completion(service)

    # The seeded demo project counts too — a reindex covers the installation.
    assert service.progress.total_projects >= 1
    assert service.progress.done_projects == service.progress.total_projects
    assert service.progress.entities_indexed >= 1
    assert service.progress.current_project is None
    assert service.progress.model_id == "fake-model"


@pytest.mark.asyncio
async def test_knowledge_sources_are_re_embedded_from_their_files(
    app: FastAPI, client: TestClient, project_id: str, service: ReindexService
) -> None:
    upload = client.post(
        f"/api/projects/{project_id}/knowledge",
        files={
            "file": (
                "setting.txt",
                b"The city of Varn stands on salt cliffs.",
                "text/plain",
            )
        },
    )
    assert upload.status_code == 201

    await _run_to_completion(service)

    assert service.progress.sources_indexed >= 1
    listed = client.get(f"/api/projects/{project_id}/knowledge").json()
    # Rebuilt, not orphaned: the source is usable again right after.
    assert listed[0]["status"] == "ready"


@pytest.mark.asyncio
async def test_second_reindex_is_refused_while_one_runs(
    service: ReindexService,
) -> None:
    service.start()
    try:
        with pytest.raises(ReindexInProgressError):
            service.start()
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_disabled_embeddings_make_it_a_no_op(
    client: TestClient, app: FastAPI, settings: Settings, store: RecordingVectorStore
) -> None:
    def build_nothing(_settings: Settings) -> EmbeddingProvider | None:
        return None

    def build_store(
        _settings: Settings, embedder: EmbeddingProvider | None
    ) -> RecordingVectorStore | None:
        return store if embedder is not None else None

    disabled_stack = EmbeddingStack(settings, build_store, build_nothing)
    service = ReindexService(
        app.state.session_factory, app.state.store_factories, disabled_stack
    )

    await _run_to_completion(service)

    assert service.progress.state == "done"
    assert store.upserted == {}


@pytest.mark.asyncio
async def test_failure_is_reported_not_raised(
    client: TestClient, app: FastAPI, settings: Settings, stack: EmbeddingStack
) -> None:
    class BrokenFactories:
        def __getattr__(self, name: str) -> Any:
            raise RuntimeError("storage is unavailable")

    service = ReindexService(
        app.state.session_factory, cast(Any, BrokenFactories()), stack
    )

    await _run_to_completion(service)

    # A failed rebuild leaves a readable status behind instead of taking the
    # app down with it.
    assert service.progress.state == "error"
    assert service.progress.error is not None
