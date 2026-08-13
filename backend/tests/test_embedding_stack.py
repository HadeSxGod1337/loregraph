"""Swapping the embedding stack at runtime, and what that implies for the
stored vectors."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from loregraph.config import Settings
from loregraph.llm.embeddings import EmbeddingProvider
from loregraph.services.embedding_stack import EmbeddingStack
from loregraph.storage.vectorstore.protocols import LoreChunk, RetrievedChunk


class FakeEmbedder:
    """Names itself after the configured model without loading anything."""

    def __init__(self, model_id: str) -> None:
        self._model_id = model_id
        self.embedded: list[str] = []

    @property
    def model_id(self) -> str:
        return self._model_id

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.embedded.extend(texts)
        return [[0.0, 1.0] for _ in texts]


class FakeVectorStore:
    def __init__(self, embedder: EmbeddingProvider) -> None:
        self.embedder = embedder

    async def upsert(self, project_id: str, chunks: Sequence[LoreChunk]) -> None: ...

    async def delete(self, project_id: str, entity_ids: Sequence[str]) -> None: ...

    async def query(
        self, project_id: str, text: str, k: int = 5
    ) -> list[RetrievedChunk]:
        return []

    async def drop_project(self, project_id: str) -> None: ...


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    kwargs: dict[str, Any] = {
        "data_dir": tmp_path,
        "embedding_provider": "local",
        "_env_file": None,
        **overrides,
    }
    return Settings(**kwargs)


def build_embedder(settings: Settings) -> EmbeddingProvider | None:
    if settings.embedding_provider == "disabled":
        return None
    return FakeEmbedder(settings.embedding_model)


def build_store(
    settings: Settings, embedder: EmbeddingProvider | None
) -> FakeVectorStore | None:
    return FakeVectorStore(embedder) if embedder is not None else None


def make_stack(settings: Settings) -> EmbeddingStack:
    return EmbeddingStack(settings, build_store, build_embedder)


@pytest.mark.asyncio
async def test_disabled_provider_yields_no_indexes(tmp_path: Path) -> None:
    stack = make_stack(make_settings(tmp_path, embedding_provider="disabled"))

    # The manual editor keeps working with no vector layer at all — every
    # consumer treats None as "degrade", never as an error.
    assert stack.vector_index is None
    assert stack.knowledge_index is None
    assert stack.model_id is None


@pytest.mark.asyncio
async def test_changing_the_model_requires_a_reindex(tmp_path: Path) -> None:
    stack = make_stack(make_settings(tmp_path, embedding_model="model-a"))

    changed = await stack.rebuild(make_settings(tmp_path, embedding_model="model-b"))

    assert changed is True
    assert stack.model_id == "model-b"


@pytest.mark.asyncio
async def test_rebuilding_with_the_same_model_requires_no_reindex(
    tmp_path: Path,
) -> None:
    stack = make_stack(make_settings(tmp_path, embedding_model="model-a"))

    changed = await stack.rebuild(make_settings(tmp_path, embedding_model="model-a"))

    assert changed is False


@pytest.mark.asyncio
async def test_turning_embeddings_off_and_on_again(tmp_path: Path) -> None:
    stack = make_stack(make_settings(tmp_path, embedding_model="model-a"))

    await stack.rebuild(make_settings(tmp_path, embedding_provider="disabled"))
    assert stack.vector_index is None

    changed = await stack.rebuild(make_settings(tmp_path, embedding_model="model-a"))

    assert stack.vector_index is not None
    # Vectors were dropped while off, so coming back is still a reindex.
    assert changed is True


@pytest.mark.asyncio
async def test_both_indexes_share_one_vector_store(tmp_path: Path) -> None:
    # A second store on the same directory would mean a second Chroma client;
    # the knowledge base is a namespace, not a separate database.
    stack = make_stack(make_settings(tmp_path))

    assert stack.vector_index is not None
    assert stack.knowledge_index is not None
    assert stack.vector_index._store is stack.knowledge_index._store


@pytest.mark.asyncio
async def test_warmup_survives_a_failing_embedder(tmp_path: Path) -> None:
    class BrokenEmbedder(FakeEmbedder):
        async def embed(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("model file is corrupt")

    def build_broken(settings: Settings) -> EmbeddingProvider | None:
        return BrokenEmbedder("broken")

    stack = EmbeddingStack(make_settings(tmp_path), build_store, build_broken)

    # Startup must not fail because a model couldn't be preloaded.
    await stack.warmup()
