import pytest

from loregraph.schemas.formula import FormulaSyntaxError, parse_dependencies

# This table is mirrored in frontend/src/components/sheet/widgets/formula.ts's
# own test/example set to keep the two independent grammar implementations
# honest against each other.
VALID_CASES: list[tuple[str, frozenset[str]]] = [
    ("1", frozenset()),
    ("str", frozenset({"str"})),
    ("floor((str - 10) / 2)", frozenset({"str"})),
    (
        "floor((dex - 10) / 2) + (prof_stealth ? proficiency : 0)",
        frozenset({"dex", "prof_stealth", "proficiency"}),
    ),
    ("max(a, b, c)", frozenset({"a", "b", "c"})),
    ("min(1, 2)", frozenset()),
    ("a == b && c != d", frozenset({"a", "b", "c", "d"})),
    ("a || b && !c", frozenset({"a", "b", "c"})),
    ("-x + -1", frozenset({"x"})),
    ("(a + b) * (c - d)", frozenset({"a", "b", "c", "d"})),
    ("round(a % b, 2)", frozenset({"a", "b"})),
    ("a >= b ? c : d", frozenset({"a", "b", "c", "d"})),
    ("a ? b ? c : d : e", frozenset({"a", "b", "c", "d", "e"})),
]

INVALID_CASES: list[str] = [
    "",
    "   ",
    "1 +",
    "+ 1",
    "(1 + 2",
    "1 + 2)",
    "unknown_fn(1)",
    "a ? b",
    "a ? b :",
    "1 2",
    "a &&",
    "@bad",
    "1..5",
]


@pytest.mark.parametrize(("formula", "expected"), VALID_CASES)
def test_parse_dependencies_valid(formula: str, expected: frozenset[str]) -> None:
    assert parse_dependencies(formula) == expected


@pytest.mark.parametrize("formula", INVALID_CASES)
def test_parse_dependencies_rejects_invalid_syntax(formula: str) -> None:
    with pytest.raises(FormulaSyntaxError):
        parse_dependencies(formula)


def test_function_call_name_is_not_a_dependency() -> None:
    assert parse_dependencies("floor(x)") == frozenset({"x"})


def test_ternary_is_right_associative_and_collects_both_branches() -> None:
    assert parse_dependencies("a ? b : c ? d : e") == frozenset(
        {"a", "b", "c", "d", "e"}
    )
