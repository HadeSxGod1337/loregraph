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

import asyncio
import logging
from dataclasses import dataclass

from loregraph.schemas.entity import EntityOut
from loregraph.services.vector_index import VectorIndex, entity_to_text
from loregraph.storage.protocols import EntityStore
from loregraph.storage.vectorstore.hybrid_search import (
    bm25_rank,
    reciprocal_rank_fusion,
    tokenize,
)

logger = logging.getLogger(__name__)

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


def _exact_title_ids(entities: list[EntityOut], query: str) -> list[str]:
    """Ids of entities whose title IS the query, case-folded — an obvious
    exact-name hit. Surfaced ahead of the fused ranking so a poor embedding
    rank can never bury the very entity the game master named (the priority
    order is exact title → lexical → dense, not "whatever the embedder liked").
    Several ids means several namesakes: the caller shows them all, and the
    assistant asks which one when context can't tell them apart."""
    needle = query.strip().casefold()
    if not needle:
        return []
    return [
        entity.id for entity in entities if entity.title.strip().casefold() == needle
    ]


async def _dense_ranking(
    vector_index: VectorIndex | None,
    project_id: str,
    query: str,
    *,
    limit: int,
    entity_type: str | None,
    by_id: dict[str, EntityOut],
) -> list[str]:
    """The dense (embedding) contour, degrading to empty on operational failure.

    Dense retrieval is best-effort here: if the embedding provider or the vector
    store is down, the lexical contour must still answer and the failure must
    not be read as "no such lore exists". The embedder and Chroma raise their
    own unrelated exception types (none in loregraph's domain hierarchy), so the
    catch is deliberately broad — but it re-raises cancellation and logs a
    traceback, so a real bug is observable rather than silently swallowed. Same
    degradation contract as retrieve_context's external grounding."""
    if vector_index is None:
        return []
    try:
        # Over-fetched when a type filter is on: filtering after retrieval would
        # otherwise silently return fewer than `limit` dense hits.
        chunks = await vector_index.query(
            project_id, query, k=limit * 2 if entity_type else limit
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning(
            "Dense retrieval failed for project %s; using lexical results only.",
            project_id,
            exc_info=True,
        )
        return []
    # Ids absent from by_id are either another project's or a stale index entry;
    # the SQL side is the source of truth, so they are dropped.
    return [chunk.entity_id for chunk in chunks if chunk.entity_id in by_id][:limit]


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
    dense_ids = await _dense_ranking(
        vector_index,
        project_id,
        query,
        limit=limit,
        entity_type=entity_type,
        by_id=by_id,
    )

    fused = reciprocal_rank_fusion([dense_ids, lexical_ids])
    # Exact-title hits jump the queue: whatever the embedder ranked, the entity
    # the game master named by its exact title comes first. dict.fromkeys keeps
    # first occurrence, so an exact hit already in `fused` is only promoted, not
    # duplicated, and `total` still counts distinct matches.
    ordered = list(dict.fromkeys([*_exact_title_ids(entities, query), *fused]))
    return LoreSearchResult(
        entities=[by_id[entity_id] for entity_id in ordered[:limit]],
        total=len(ordered),
    )
