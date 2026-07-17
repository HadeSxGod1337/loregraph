"""Pure lexical-ranking helpers for ChromaVectorStore's hybrid query.

Deterministic like XPBudgetCalculator (CLAUDE.md, "LLM для творчества,
Python для арифметики"): BM25 scoring and rank fusion are arithmetic, not
judgment, so they live here as plain functions ChromaVectorStore.query()
calls into — no Chroma, no embeddings, no I/O, unit-testable on their own.

`tokenize` is intentionally language-agnostic (regex word-splitting, no
stemming/lemmatization): Loregraph's campaigns span whatever language each
DM runs their table in (see llm/embeddings.py's multilingual default), so a
language-specific analyzer would help one audience and silently do nothing
— or actively hurt — for every other script.
"""

import re
from collections.abc import Sequence

from rank_bm25 import BM25Okapi

# Standard RRF damping constant (Cormack et al., 2009) — large enough that
# no single ranker's rank-1 item automatically dominates the fused order.
RRF_RANK_CONSTANT = 60

_WORD_PATTERN = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """Lowercased word tokens, any script — no stemming/lemmatization."""
    return _WORD_PATTERN.findall(text.lower())


def bm25_rank(documents: dict[str, str], query: str) -> list[str]:
    """Ranks `documents` (id -> text) against `query` by BM25 score,
    descending. Ties (including an all-zero-score query) keep the input
    dict's insertion order — deterministic, not an arbitrary hash order."""
    if not documents:
        return []
    ids = list(documents.keys())
    corpus = [tokenize(documents[doc_id]) for doc_id in ids]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(range(len(ids)), key=lambda i: scores[i], reverse=True)
    return [ids[i] for i in ranked]


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]], k: int = RRF_RANK_CONSTANT
) -> list[str]:
    """Merges several ranked id lists (e.g. dense-similarity order and BM25
    order) into one: id -> sum(1 / (k + rank)) across every list it appears
    in, then sorted descending. An id absent from a ranking simply gets no
    contribution from it, so a lexical-only or semantic-only hit can still
    surface (RRF, Cormack et al. 2009)."""
    scores: dict[str, float] = {}
    order: list[str] = []
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            if doc_id not in scores:
                order.append(doc_id)
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    # Stable sort: ids tied on fused score keep their first-seen order
    # instead of an arbitrary one.
    return sorted(order, key=lambda doc_id: scores[doc_id], reverse=True)
