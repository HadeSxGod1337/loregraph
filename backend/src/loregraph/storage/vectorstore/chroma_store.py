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
_ENTITY_ID_METADATA_KEY = "entity_id"
# Bumped whenever the physical layout of a collection changes in a way that
# makes previously written records unreadable — currently: records used to be
# keyed by the bare entity id with no metadata at all, so nothing could map a
# hit back to its entity or delete an entity's other chunks. Handled by the
# exact same drop-and-require-reindex path as an embedding model change, for
# the same reason: what is on disk cannot be interpreted by this code.
_CHUNK_SCHEMA_METADATA_KEY = "chunk_schema"
_CHUNK_SCHEMA = "entity-chunks-v1"

# How many dense-similarity candidates to pull before lexical (BM25) rank
# fusion picks the final top-k — wide enough that a strong exact/near-exact
# term match which dense similarity alone ranked outside k still gets a shot
# at surfacing (the en_dragon_threat gap from the retrieval eval), bounded so
# a query against a large project stays O(pool), not O(collection).
HYBRID_POOL_MULTIPLIER = 4
HYBRID_POOL_MIN_CANDIDATES = 20


def _record_id(chunk: LoreChunk) -> str:
    """Chroma's primary key for one chunk. Entity id first so a record stays
    greppable back to its entity when reading the raw collection."""
    return f"{chunk.entity_id}#{chunk.chunk_index}"


def _entity_id_of(record_id: str) -> str:
    """Fallback for a record whose metadata is missing — only reachable if a
    collection were written by something other than `upsert` above."""
    return record_id.rsplit("#", 1)[0]


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

    def _current_metadata(self) -> dict[str, str]:
        return {
            _MODEL_METADATA_KEY: self._embedder.model_id,
            _CHUNK_SCHEMA_METADATA_KEY: _CHUNK_SCHEMA,
        }

    def _collection_sync(self, project_id: str) -> Collection:
        name = f"p_{project_id}"
        wanted = self._current_metadata()
        collection = self._client.get_or_create_collection(name, metadata=wanted)
        stored = collection.metadata or {}
        stale = {
            key: stored.get(key)
            for key, value in wanted.items()
            if stored.get(key) != value
        }
        if stale:
            logger.warning(
                "Collection %s is stale (%s; current is %s) — dropping it; run "
                "a project reindex to rebuild.",
                name,
                stale,
                wanted,
            )
            self._client.delete_collection(name)
            collection = self._client.get_or_create_collection(name, metadata=wanted)
        return collection

    def collection_is_stale(self, project_id: str) -> bool:
        """Whether the persisted collection was built by a configuration this
        process cannot read — without dropping it.

        `_collection_sync` repairs by deleting, which is right at the point of
        use but useless as a health check: it would report "fine" precisely
        because it just destroyed the evidence. Startup asks this instead, so
        the user can be told a reindex is needed before their first search
        silently returns nothing (see api/routers/settings.py).
        """
        name = f"p_{project_id}"
        try:
            stored = self._client.get_collection(name).metadata or {}
        except NotFoundError:
            return False  # nothing indexed yet is not the same as stale
        return any(
            stored.get(key) != value for key, value in self._current_metadata().items()
        )

    async def upsert(self, project_id: str, chunks: Sequence[LoreChunk]) -> None:
        if not chunks:
            return
        embeddings = await self._embedder.embed([chunk.text for chunk in chunks])
        collection = await asyncio.to_thread(self._collection_sync, project_id)
        await asyncio.to_thread(
            collection.upsert,
            ids=[_record_id(chunk) for chunk in chunks],
            # Chroma's type stubs want numpy arrays; plain float lists are
            # accepted at runtime and keep the Protocol numpy-free.
            embeddings=cast(Any, embeddings),
            documents=[chunk.text for chunk in chunks],
            # The entity id has to survive as data, not just as an id prefix:
            # it is how a hit is mapped back to its entity and how delete
            # finds every chunk of one entity without knowing how many exist.
            metadatas=cast(
                Any, [{_ENTITY_ID_METADATA_KEY: chunk.entity_id} for chunk in chunks]
            ),
        )

    async def delete(self, project_id: str, entity_ids: Sequence[str]) -> None:
        if not entity_ids:
            return
        collection = await asyncio.to_thread(self._collection_sync, project_id)
        # By filter, not by id: an entity that was re-chunked into fewer
        # pieces would leave orphans behind if we deleted the ids we happen
        # to be able to guess.
        await asyncio.to_thread(
            collection.delete,
            where=cast(Any, {_ENTITY_ID_METADATA_KEY: {"$in": list(entity_ids)}}),
        )

    async def query(
        self, project_id: str, text: str, k: int = 5
    ) -> list[RetrievedChunk]:
        """Hybrid retrieval: dense (embedding) similarity and BM25 lexical
        match over the same candidate pool, merged by reciprocal rank fusion
        (see storage/vectorstore/hybrid_search.py). Pure dense search misses
        exact-term/name matches a much smaller local embedder ranks poorly —
        BM25 catches those without any language-specific analysis.

        Ranking happens over chunks, but `k` counts *entities*: several chunks
        of one long entity must not crowd out every other result, so the
        best-ranked chunk represents its entity and the rest are folded away.
        """
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
            include=["documents", "distances", "metadatas"],
        )
        record_ids = result["ids"][0]
        documents = (result.get("documents") or [[]])[0] or []
        distances = (result.get("distances") or [[]])[0] or []
        metadatas = (result.get("metadatas") or [[]])[0] or []
        # Chroma returns a distance (lower = closer); keep a similarity-like
        # score (higher = closer) for the final RetrievedChunk, same
        # semantics as before hybrid fusion was added.
        texts_by_record = dict(zip(record_ids, documents, strict=True))
        similarity_by_record = {
            record_id: 1.0 - distance
            for record_id, distance in zip(record_ids, distances, strict=True)
        }
        entity_by_record = {
            record_id: str(
                (metadata or {}).get(_ENTITY_ID_METADATA_KEY)
                or _entity_id_of(record_id)
            )
            for record_id, metadata in zip(record_ids, metadatas, strict=True)
        }

        lexical_ids = bm25_rank(texts_by_record, text)
        fused_records = reciprocal_rank_fusion([record_ids, lexical_ids])

        chunks: list[RetrievedChunk] = []
        seen: set[str] = set()
        for record_id in fused_records:
            entity_id = entity_by_record[record_id]
            if entity_id in seen:
                continue
            seen.add(entity_id)
            chunks.append(
                RetrievedChunk(
                    entity_id=entity_id,
                    text=texts_by_record.get(record_id, ""),
                    score=similarity_by_record.get(record_id, 0.0),
                )
            )
            if len(chunks) == k:
                break
        return chunks

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
