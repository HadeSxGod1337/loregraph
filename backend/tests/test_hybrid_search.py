import pytest

from loregraph.storage.vectorstore.hybrid_search import (
    bm25_rank,
    reciprocal_rank_fusion,
    tokenize,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Guard Tomas", ["guard", "tomas"]),
        ("Мира Кузнец", ["мира", "кузнец"]),
        ("café-owner_42", ["café", "owner_42"]),
        ("", []),
    ],
)
def test_tokenize(text: str, expected: list[str]) -> None:
    assert tokenize(text) == expected


def test_bm25_rank_empty_documents_returns_empty() -> None:
    assert bm25_rank({}, "anything") == []


def test_bm25_rank_ranks_exact_term_match_first() -> None:
    documents = {
        "a": "Guard Tomas secretly feeds patrol schedules to the thieves' guild.",
        "b": "Guard Bren patrols the north wall, nothing unusual about him.",
        "c": "Rina the Trader sells potions in the market square.",
    }
    ranked = bm25_rank(documents, "thieves guild")
    assert ranked[0] == "a"


def test_bm25_rank_ties_keep_input_order() -> None:
    documents = {"x": "irrelevant text", "y": "irrelevant text"}
    assert bm25_rank(documents, "query with no overlap") == ["x", "y"]


def test_reciprocal_rank_fusion_agreement_wins() -> None:
    dense = ["b", "a", "c"]
    lexical = ["a", "b", "c"]
    # "a" and "b" are both top-2 in one ranking and top-2 in the other;
    # "c" is last in both — it must end up last in the fusion too.
    fused = reciprocal_rank_fusion([dense, lexical])
    assert fused[-1] == "c"
    assert set(fused[:2]) == {"a", "b"}


def test_reciprocal_rank_fusion_surfaces_lexical_only_hit() -> None:
    # "z" never appears in the dense ranking at all (e.g. it fell outside
    # the dense candidate pool) but is the strongest lexical match.
    dense = ["a", "b", "c"]
    lexical = ["z", "a", "b"]
    fused = reciprocal_rank_fusion([dense, lexical])
    assert "z" in fused


def test_reciprocal_rank_fusion_empty_rankings_returns_empty() -> None:
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []
