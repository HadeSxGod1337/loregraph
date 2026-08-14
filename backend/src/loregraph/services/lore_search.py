"""Searching the world's canon: dense retrieval and lexical matching, fused.

ChromaVectorStore.query already fuses BM25 into its own result, but only over
the pool of candidates *dense similarity produced first* (see
storage/vectorstore/chroma_store.py's HYBRID_POOL_* constants). An exact name
the embedder ranked nowhere near the top therefore stays unreachable no matter
how good the embedding model is — which is why swapping local embeddings for a
hosted provider did nothing for "find me the character called X".

So the lexical contour is run here instead, against SQLite (the source of
truth, and never stale relative to the index), and merged with the dense
ranking through the same reciprocal_rank_fusion the store uses. A term match
and a meaning match each get to surface a result the other missed.

Matching is deliberately morphology-free — Loregraph's campaigns are written
in whatever language the table runs in, so a Russian or German stemmer would
help one audience and quietly mislead every other. Prefix agreement in either
direction ("егоров" vs "егор") buys most of what stemming would, in every
script, with no language table.
"""

from dataclasses import dataclass

from loregraph.schemas.entity import EntityOut
from loregraph.services.vector_index import VectorIndex, entity_to_text
from loregraph.storage.protocols import EntityStore
from loregraph.storage.vectorstore.hybrid_search import (
    bm25_rank,
    reciprocal_rank_fusion,
    tokenize,
)

# Below this, a token is too generic for prefix agreement to mean anything —
# "а"/"of" would match half the world and drown the real hits.
MIN_LEXICAL_TOKEN_CHARS = 3
# Ceiling on how many lexically-matching entities get scored by BM25. A very
# common word can match most of a big campaign; ranking is O(candidates), and
# past a couple hundred the tail could not reach the shown top-k anyway.
LEXICAL_CANDIDATE_LIMIT = 200


@dataclass(frozen=True)
class LoreSearchResult:
    """`entities` is already cut to the caller's limit; `total` is how many
    matched before that cut, so the caller can say so out loud instead of
    passing a truncated list off as the whole answer."""

    entities: list[EntityOut]
    total: int


def _matches_lexically(entity: EntityOut, query_tokens: set[str], needle: str) -> bool:
    haystack = f"{entity.title}\n{entity_to_text(entity)}".casefold()
    if needle and needle in haystack:
        return True
    return any(
        token.startswith(query_token) or query_token.startswith(token)
        for token in tokenize(haystack)
        if len(token) >= MIN_LEXICAL_TOKEN_CHARS
        for query_token in query_tokens
    )


def _lexical_ranking(entities: list[EntityOut], query: str) -> list[str]:
    query_tokens = {
        token for token in tokenize(query) if len(token) >= MIN_LEXICAL_TOKEN_CHARS
    }
    needle = query.strip().casefold()
    if not query_tokens and not needle:
        return []
    candidates = [
        entity
        for entity in entities
        if _matches_lexically(entity, query_tokens, needle)
    ][:LEXICAL_CANDIDATE_LIMIT]
    if not candidates:
        return []
    return bm25_rank(
        {entity.id: entity_to_text(entity) for entity in candidates}, query
    )


async def search_lore(
    *,
    vector_index: VectorIndex | None,
    entity_store: EntityStore,
    project_id: str,
    query: str,
    limit: int,
    entity_type: str | None = None,
) -> LoreSearchResult:
    """Best matches for `query`, plus how many matched in total.

    Degrades to the lexical contour alone when embeddings are disabled — the
    same code path with one input missing, not a separate fallback branch.
    """
    entities = await entity_store.list_entities(project_id, entity_type)
    by_id = {entity.id: entity for entity in entities}

    lexical_ids = _lexical_ranking(entities, query)

    dense_ids: list[str] = []
    if vector_index is not None:
        # Over-fetched when a type filter is on: filtering after retrieval
        # would otherwise silently return fewer than `limit` dense hits.
        chunks = await vector_index.query(
            project_id, query, k=limit * 2 if entity_type else limit
        )
        # Ids absent from by_id are either another project's or a stale index
        # entry; the SQL side is the source of truth, so they are dropped.
        dense_ids = [chunk.entity_id for chunk in chunks if chunk.entity_id in by_id][
            :limit
        ]

    fused = reciprocal_rank_fusion([dense_ids, lexical_ids])
    return LoreSearchResult(
        entities=[by_id[entity_id] for entity_id in fused[:limit]],
        total=len(fused),
    )
