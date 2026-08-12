"""Formula grammar for computed sheet widgets — a deliberately small
expression language, not arbitrary Python `eval` (injection risk, unbounded
runtime). This module only *validates*: it checks syntax and extracts the
field keys a formula references. Evaluating a formula against live entity
values is a frontend concern (components/sheet/widgets/formula.ts, which
re-implements this grammar) — the backend has no entity field values to
compute against at template-save time, only field_defs to validate references
against. The two must be changed together: this module's tests cover the
grammar, the evaluator has none of its own, so a token added here and missed
there surfaces only as a sheet showing 0.

Grammar (EBNF)::

    expr           := ternary
    ternary        := logic_or ( "?" expr ":" expr )?
    logic_or       := logic_and ( "||" logic_and )*
    logic_and      := equality ( "&&" equality )*
    equality       := comparison ( ("==" | "!=") comparison )*
    comparison     := additive ( ("<" | "<=" | ">" | ">=") additive )*
    additive       := multiplicative ( ("+" | "-") multiplicative )*
    multiplicative := unary ( ("*" | "/" | "%") unary )*
    unary          := ("!" | "-")? primary
    primary        := NUMBER | IDENT | "(" expr ")" | IDENT "(" (expr ("," expr)*)? ")"

`IDENT` not immediately followed by `(` is a field-key reference; `IDENT(`
is a call to one of ALLOWED_FUNCTIONS.
"""

from collections.abc import Callable
from dataclasses import dataclass

ALLOWED_FUNCTIONS: frozenset[str] = frozenset(
    {"floor", "ceil", "round", "min", "max", "abs"}
)

_OPERATORS = (
    "<=",
    ">=",
    "==",
    "!=",
    "&&",
    "||",
    "?",
    ":",
    "<",
    ">",
    "+",
    "-",
    "*",
    "/",
    "%",
    "!",
    "(",
    ")",
    ",",
)


class FormulaSyntaxError(ValueError):
    """A computed-widget formula does not match the expression grammar."""


@dataclass(frozen=True)
class _Token:
    kind: str  # "number" | "ident" | "op" | "end"
    value: str


def _tokenize(source: str) -> list[_Token]:
    tokens: list[_Token] = []
    pos = 0
    length = len(source)
    while pos < length:
        ch = source[pos]
        if ch.isspace():
            pos += 1
            continue
        if ch.isdigit():
            start = pos
            while pos < length and source[pos].isdigit():
                pos += 1
            if (
                pos < length
                and source[pos] == "."
                and pos + 1 < length
                and source[pos + 1].isdigit()
            ):
                pos += 1
                while pos < length and source[pos].isdigit():
                    pos += 1
            tokens.append(_Token("number", source[start:pos]))
            continue
        if ch.isalpha() or ch == "_":
            start = pos
            while pos < length and (source[pos].isalnum() or source[pos] == "_"):
                pos += 1
            tokens.append(_Token("ident", source[start:pos]))
            continue
        for op in _OPERATORS:
            if source.startswith(op, pos):
                tokens.append(_Token("op", op))
                pos += len(op)
                break
        else:
            raise FormulaSyntaxError(f"unexpected character {ch!r} at position {pos}")
    tokens.append(_Token("end", ""))
    return tokens


class _Parser:
    """Recursive-descent parser that validates syntax without ever computing
    a value — it only walks the grammar and records which identifiers were
    referenced as field keys (as opposed to function-call names)."""

    def __init__(self, tokens: list[_Token]) -> None:
        self._tokens = tokens
        self._pos = 0
        self.dependencies: set[str] = set()

    def _peek(self) -> _Token:
        return self._tokens[self._pos]

    def _advance(self) -> _Token:
        token = self._tokens[self._pos]
        self._pos += 1
        return token

    def _at_op(self, op: str) -> bool:
        token = self._peek()
        return token.kind == "op" and token.value == op

    def _expect_op(self, op: str) -> None:
        if not self._at_op(op):
            raise FormulaSyntaxError(f"expected {op!r}, found {self._peek().value!r}")
        self._advance()

    def parse(self) -> None:
        self._expr()
        if self._peek().kind != "end":
            raise FormulaSyntaxError(
                f"unexpected trailing token {self._peek().value!r}"
            )

    def _expr(self) -> None:
        self._ternary()

    def _ternary(self) -> None:
        self._logic_or()
        if self._at_op("?"):
            self._advance()
            self._expr()
            self._expect_op(":")
            self._expr()

    def _binary_level(
        self, next_level: Callable[[], None], ops: tuple[str, ...]
    ) -> None:
        next_level()
        while self._peek().kind == "op" and self._peek().value in ops:
            self._advance()
            next_level()

    def _logic_or(self) -> None:
        self._binary_level(self._logic_and, ("||",))

    def _logic_and(self) -> None:
        self._binary_level(self._equality, ("&&",))

    def _equality(self) -> None:
        self._binary_level(self._comparison, ("==", "!="))

    def _comparison(self) -> None:
        self._binary_level(self._additive, ("<", "<=", ">", ">="))

    def _additive(self) -> None:
        self._binary_level(self._multiplicative, ("+", "-"))

    def _multiplicative(self) -> None:
        self._binary_level(self._unary, ("*", "/", "%"))

    def _unary(self) -> None:
        token = self._peek()
        if token.kind == "op" and token.value in ("!", "-"):
            self._advance()
            self._unary()
            return
        self._primary()

    def _primary(self) -> None:
        token = self._advance()
        if token.kind == "number":
            return
        if token.kind == "ident":
            if self._at_op("("):
                if token.value not in ALLOWED_FUNCTIONS:
                    raise FormulaSyntaxError(f"unknown function {token.value!r}")
                self._advance()
                if not self._at_op(")"):
                    self._expr()
                    while self._at_op(","):
                        self._advance()
                        self._expr()
                self._expect_op(")")
                return
            self.dependencies.add(token.value)
            return
        if token.kind == "op" and token.value == "(":
            self._expr()
            self._expect_op(")")
            return
        raise FormulaSyntaxError(f"unexpected token {token.value!r}")


def parse_dependencies(formula: str) -> frozenset[str]:
    """Validate a computed-widget formula and return the field keys it
    references. Raises FormulaSyntaxError on invalid syntax, an unbalanced
    expression, or a call to a function outside ALLOWED_FUNCTIONS."""
    if not formula.strip():
        raise FormulaSyntaxError("formula must not be empty")
    parser = _Parser(_tokenize(formula))
    parser.parse()
    return frozenset(parser.dependencies)
