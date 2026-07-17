import asyncio
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings as ChromaSettings
from chromadb.errors import NotFoundError

from loregraph.llm.embeddings import EmbeddingProvider
from loregraph.storage.vectorstore.hybrid_search import (
    bm25_rank,
    reciprocal_rank_fusion,
)
from loregraph.storage.vectorstore.protocols import LoreChunk, RetrievedChunk

logger = logging.getLogger(__name__)

_MODEL_METADATA_KEY = "embedding_model"

# How many dense-similarity candidates to pull before lexical (BM25) rank
# fusion picks the final top-k — wide enough that a strong exact/near-exact
# term match which dense similarity alone ranked outside k still gets a shot
# at surfacing (the en_dragon_threat gap from the retrieval eval), bounded so
# a query against a large project stays O(pool), not O(collection).
HYBRID_POOL_MULTIPLIER = 4
HYBRID_POOL_MIN_CANDIDATES = 20


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
        """Hybrid retrieval: dense (embedding) similarity and BM25 lexical
        match over the same candidate pool, merged by reciprocal rank fusion
        (see storage/vectorstore/hybrid_search.py). Pure dense search misses
        exact-term/name matches a much smaller local embedder ranks poorly —
        BM25 catches those without any language-specific analysis."""
        collection = await asyncio.to_thread(self._collection_sync, project_id)
        count = await asyncio.to_thread(collection.count)
        if count == 0:
            return []
        pool_size = min(
            count, max(k * HYBRID_POOL_MULTIPLIER, HYBRID_POOL_MIN_CANDIDATES)
        )

        embedding = (await self._embedder.embed([text]))[0]
        result = await asyncio.to_thread(
            collection.query,
            query_embeddings=cast(Any, [embedding]),
            n_results=pool_size,
            include=["documents", "distances"],
        )
        dense_ids = result["ids"][0]
        documents = (result.get("documents") or [[]])[0] or []
        distances = (result.get("distances") or [[]])[0] or []
        # Chroma returns a distance (lower = closer); keep a similarity-like
        # score (higher = closer) for the final RetrievedChunk, same
        # semantics as before hybrid fusion was added.
        texts_by_id = dict(zip(dense_ids, documents, strict=True))
        similarity_by_id = {
            entity_id: 1.0 - distance
            for entity_id, distance in zip(dense_ids, distances, strict=True)
        }

        lexical_ids = bm25_rank(texts_by_id, text)
        fused_ids = reciprocal_rank_fusion([dense_ids, lexical_ids])[:k]

        return [
            RetrievedChunk(
                entity_id=entity_id,
                text=texts_by_id.get(entity_id, ""),
                score=similarity_by_id.get(entity_id, 0.0),
            )
            for entity_id in fused_ids
        ]

    async def drop_project(self, project_id: str) -> None:
        def _drop() -> None:
            try:
                self._client.delete_collection(f"p_{project_id}")
            except NotFoundError:
                # Only the benign case is swallowed; a real I/O/permission
                # failure propagates to the caller (which treats drops as
                # best-effort and logs it properly).
                logger.debug("No vector collection to drop for %s", project_id)

        await asyncio.to_thread(_drop)
