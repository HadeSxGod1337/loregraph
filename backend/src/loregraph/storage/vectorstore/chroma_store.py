import asyncio
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings as ChromaSettings

from loregraph.llm.embeddings import EmbeddingProvider
from loregraph.storage.vectorstore.protocols import LoreChunk, RetrievedChunk

logger = logging.getLogger(__name__)

_MODEL_METADATA_KEY = "embedding_model"


class ChromaVectorStore:
    """Embedded Chroma (PersistentClient), one collection per project.

    Embeddings are computed by the injected EmbeddingProvider, never by
    Chroma's own default embedder — that keeps the provider swappable and the
    model id auditable. If a collection was built with a different model, it
    is dropped and recreated empty (embeddings across models are not
    comparable); a reindex rebuilds it from SQLite.
    """

    def __init__(self, path: Path, embedder: EmbeddingProvider) -> None:
        self._embedder = embedder
        # anonymized_telemetry=False: local self-hosted tool, no phone-home.
        self._client: ClientAPI = chromadb.PersistentClient(
            path=str(path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )

    def _collection_sync(self, project_id: str) -> Collection:
        name = f"p_{project_id}"
        collection = self._client.get_or_create_collection(
            name, metadata={_MODEL_METADATA_KEY: self._embedder.model_id}
        )
        stored_model = (collection.metadata or {}).get(_MODEL_METADATA_KEY)
        if stored_model != self._embedder.model_id:
            logger.warning(
                "Collection %s was built with embedding model %r, current is %r "
                "— dropping it; run a project reindex to rebuild.",
                name,
                stored_model,
                self._embedder.model_id,
            )
            self._client.delete_collection(name)
            collection = self._client.get_or_create_collection(
                name, metadata={_MODEL_METADATA_KEY: self._embedder.model_id}
            )
        return collection

    async def upsert(self, project_id: str, chunks: Sequence[LoreChunk]) -> None:
        if not chunks:
            return
        embeddings = await self._embedder.embed([chunk.text for chunk in chunks])
        collection = await asyncio.to_thread(self._collection_sync, project_id)
        await asyncio.to_thread(
            collection.upsert,
            ids=[chunk.entity_id for chunk in chunks],
            # Chroma's type stubs want numpy arrays; plain float lists are
            # accepted at runtime and keep the Protocol numpy-free.
            embeddings=cast(Any, embeddings),
            documents=[chunk.text for chunk in chunks],
        )

    async def delete(self, project_id: str, entity_ids: Sequence[str]) -> None:
        if not entity_ids:
            return
        collection = await asyncio.to_thread(self._collection_sync, project_id)
        await asyncio.to_thread(collection.delete, ids=list(entity_ids))

    async def query(
        self, project_id: str, text: str, k: int = 5
    ) -> list[RetrievedChunk]:
        embedding = (await self._embedder.embed([text]))[0]
        collection = await asyncio.to_thread(self._collection_sync, project_id)
        result = await asyncio.to_thread(
            collection.query,
            query_embeddings=cast(Any, [embedding]),
            n_results=k,
            include=["documents", "distances"],
        )
        ids = result["ids"][0]
        documents = (result.get("documents") or [[]])[0] or []
        distances = (result.get("distances") or [[]])[0] or []
        return [
            RetrievedChunk(
                entity_id=entity_id,
                text=document or "",
                # Chroma returns a distance (lower = closer); expose a
                # similarity-like score (higher = closer) to callers.
                score=1.0 - distance,
            )
            for entity_id, document, distance in zip(
                ids, documents, distances, strict=True
            )
        ]

    async def drop_project(self, project_id: str) -> None:
        def _drop() -> None:
            try:
                self._client.delete_collection(f"p_{project_id}")
            except Exception:
                logger.debug("No vector collection to drop for %s", project_id)

        await asyncio.to_thread(_drop)
