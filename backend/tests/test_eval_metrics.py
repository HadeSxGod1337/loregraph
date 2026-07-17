import pytest

from evals.metrics import (
    dcg_at_k,
    hallucination_catch_rate,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


@pytest.mark.parametrize(
    "retrieved,relevant,k,expected",
    [
        (["a", "b", "c"], {"a"}, 1, 1.0),
        (["a", "b", "c"], {"a", "z"}, 3, 0.5),
        (["b", "c", "d"], {"a"}, 3, 0.0),
        (["a"], {"a", "b"}, 1, 0.5),
    ],
)
def test_recall_at_k(
    retrieved: list[str], relevant: set[str], k: int, expected: float
) -> None:
    assert recall_at_k(retrieved, relevant, k) == expected


def test_recall_at_k_requires_relevant_ids() -> None:
    with pytest.raises(ValueError, match="relevant_ids"):
        recall_at_k(["a"], set(), 1)


@pytest.mark.parametrize(
    "retrieved,relevant,k,expected",
    [
        (["a", "b", "c"], {"a", "b"}, 2, 1.0),
        (["a", "x", "y"], {"a"}, 3, 1 / 3),
        ([], {"a"}, 5, 0.0),
    ],
)
def test_precision_at_k(
    retrieved: list[str], relevant: set[str], k: int, expected: float
) -> None:
    assert precision_at_k(retrieved, relevant, k) == pytest.approx(expected)


@pytest.mark.parametrize(
    "retrieved,relevant,expected",
    [
        (["a", "b", "c"], {"c"}, 1 / 3),
        (["a", "b", "c"], {"a"}, 1.0),
        (["a", "b", "c"], {"z"}, 0.0),
    ],
)
def test_reciprocal_rank(
    retrieved: list[str], relevant: set[str], expected: float
) -> None:
    assert reciprocal_rank(retrieved, relevant) == pytest.approx(expected)


def test_dcg_at_k_rewards_earlier_high_relevance() -> None:
    relevance = {"a": 2, "b": 1}
    earlier = dcg_at_k(["a", "b", "c"], relevance, 3)
    later = dcg_at_k(["b", "a", "c"], relevance, 3)
    assert earlier > later


def test_ndcg_at_k_perfect_ranking_is_one() -> None:
    relevance = {"a": 2, "b": 1, "c": 0}
    assert ndcg_at_k(["a", "b", "c"], relevance, 3) == pytest.approx(1.0)


def test_ndcg_at_k_no_relevant_items_is_zero() -> None:
    assert ndcg_at_k(["a", "b"], {"a": 0, "b": 0}, 2) == 0.0


def test_ndcg_at_k_worst_ranking_is_between_zero_and_one() -> None:
    relevance = {"a": 2, "b": 1, "c": 0}
    score = ndcg_at_k(["c", "b", "a"], relevance, 3)
    assert 0.0 < score < 1.0


@pytest.mark.parametrize(
    "flagged,planted,expected",
    [
        (0, 0, 1.0),
        (2, 2, 1.0),
        (1, 2, 0.5),
        (0, 2, 0.0),
        (5, 2, 1.0),  # over-flagging still caps at a perfect catch rate
    ],
)
def test_hallucination_catch_rate(flagged: int, planted: int, expected: float) -> None:
    assert hallucination_catch_rate(flagged, planted) == expected
