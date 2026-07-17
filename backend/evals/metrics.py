"""Pure retrieval/grounding quality metrics — no I/O, no model calls.

Deterministic like XPBudgetCalculator (CLAUDE.md, "LLM для творчества,
Python для арифметики"): ranking math is arithmetic, not judgment, so it
lives here as plain functions the eval scripts (which drive real embeddings
and agent nodes) call into, and that unit tests can check without a model.
"""

import math
from collections.abc import Sequence


def recall_at_k(retrieved_ids: Sequence[str], relevant_ids: set[str], k: int) -> float:
    """Fraction of relevant_ids present anywhere in the top-k retrieved_ids."""
    if not relevant_ids:
        raise ValueError("relevant_ids must be non-empty")
    top_k = set(retrieved_ids[:k])
    return len(top_k & relevant_ids) / len(relevant_ids)


def precision_at_k(
    retrieved_ids: Sequence[str], relevant_ids: set[str], k: int
) -> float:
    """Fraction of the top-k retrieved_ids that are actually relevant."""
    top_k = retrieved_ids[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for entity_id in top_k if entity_id in relevant_ids)
    return hits / len(top_k)


def reciprocal_rank(retrieved_ids: Sequence[str], relevant_ids: set[str]) -> float:
    """1/rank of the first relevant hit; 0.0 if none of retrieved_ids is
    relevant. Averaging this across queries gives MRR."""
    for rank, entity_id in enumerate(retrieved_ids, start=1):
        if entity_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def dcg_at_k(retrieved_ids: Sequence[str], relevance: dict[str, int], k: int) -> float:
    return sum(
        relevance.get(entity_id, 0) / math.log2(rank + 1)
        for rank, entity_id in enumerate(retrieved_ids[:k], start=1)
    )


def ndcg_at_k(retrieved_ids: Sequence[str], relevance: dict[str, int], k: int) -> float:
    """Graded relevance scoring (0 = irrelevant, 1 = relevant, 2 = the entity
    the query is really about) normalized against the ideal ranking. Unlike
    recall@k this rewards ranking the highly-relevant hit above a merely-
    relevant one, not just presence/absence — the "relevance scoring" metric.
    """
    actual = dcg_at_k(retrieved_ids, relevance, k)
    ideal_order = sorted(relevance.values(), reverse=True)[:k]
    ideal = sum(
        grade / math.log2(rank + 1) for rank, grade in enumerate(ideal_order, start=1)
    )
    return actual / ideal if ideal > 0 else 0.0


def hallucination_catch_rate(flagged: int, planted: int) -> float:
    """Fraction of planted hallucinated claims (fabricated citations or
    relationship targets — see evals/hallucination_cases.py) a grounding
    guard actually flagged. planted=0 (a clean draft) trivially passes: 1.0.
    """
    if planted == 0:
        return 1.0
    return min(flagged, planted) / planted
