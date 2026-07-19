"""Shared fuzzy title matching — used wherever generated content needs to be
checked against existing/other titles for near-duplicates (dedup during
chat proposals, and during bulk-import merge). A pure function, not a
class: same rationale as XPBudgetCalculator — this is deterministic string
comparison, no LLM involved.
"""

from difflib import SequenceMatcher


def title_similarity(a: str, b: str) -> float:
    """Similarity ratio in [0, 1]; case-sensitive — callers casefold first
    if they want case-insensitive matching (most do)."""
    return SequenceMatcher(None, a, b).ratio()
