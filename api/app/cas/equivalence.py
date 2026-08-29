"""Pure symbolic-equivalence check over two expression strings.

No database, no clock, no network — SymPy runs in-process and deterministically.
The single entry point is `check_equivalence`; everything else is private.

Contract (mirrors `app.practice.grading`'s "malformed grades false" stance):

- Either side unparseable — empty, bad token, a disallowed character, a stray
  `__`, or past the length cap — returns `EquivalenceOutcome.PARSE_ERROR`. The
  caller decides what that means (the grader marks it wrong; the step-check
  stays silent).
- Both sides parse and denote the same function — over the given `domain`, and
  with the named `variables` carrying that domain's assumptions —
  `EquivalenceOutcome.EQUIVALENT`.
- Both sides parse but differ — `EquivalenceOutcome.NOT_EQUIVALENT`. An internal
  SymPy failure while comparing two parsed expressions also lands here (never
  an exception out of the module).

`domain` is caller configuration, not student input: an unknown value raises
`ValueError`, the way `grading.is_correct` raises on an unknown question type.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Sequence

import sympy as sp
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

# `implicit_multiplication_application` makes `2(x+1)` and `2x` parse the way a
# student writes them; `convert_xor` reads `^` as exponentiation, not xor.
_TRANSFORMS = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
)

# The only names an expression may reference beyond its variables — the maths a
# Year 7 answer or a tutoring step actually uses. Anything else the parser would
# treat as a free symbol; keeping this list short means a typo'd function name
# can't silently become a symbol and read as "not equivalent" for a confusing
# reason.
_ALLOWED_NAMES: dict[str, object] = {
    "sin": sp.sin,
    "cos": sp.cos,
    "tan": sp.tan,
    "exp": sp.exp,
    "log": sp.log,
    "ln": sp.log,
    "sqrt": sp.sqrt,
    "Abs": sp.Abs,
    "pi": sp.pi,
    "E": sp.E,
}

# Assumptions attached to every named variable, by domain.
_DOMAIN_ASSUMPTIONS: dict[str, dict[str, bool]] = {
    "real": {"real": True},
    "positive": {"positive": True},
    "complex": {},
}

# Belt-and-braces over SymPy's own parser sandbox: an expression is math, so it
# is letters, digits, and operators only. This rejects attribute access,
# indexing, strings, and every other Python construct before `parse_expr` runs.
# It does not make everything that survives it *sensible* — `x y z` still parses
# (as `x*y*z`, via implicit multiplication) and lands on NOT_EQUIVALENT.
_ALLOWED_CHARS = re.compile(r"^[A-Za-z0-9_.,+\-*/^()\s]+$")
_MAX_EXPR_LEN = 500


class EquivalenceOutcome(str, Enum):
    """The three outcomes `check_equivalence` distinguishes.

    SymPy occasionally can't decide two parsed expressions either way; that
    undecided case is folded into `NOT_EQUIVALENT` (with `detail` saying so) —
    conservative for a grader, and the deterministic path callers get.
    """

    EQUIVALENT = "equivalent"
    NOT_EQUIVALENT = "not_equivalent"
    PARSE_ERROR = "parse_error"


@dataclass(frozen=True)
class EquivalenceResult:
    """`outcome` plus a short human-readable `detail` for logs / step-check.

    Truthy exactly when equivalent, so a grader can do
    `bool(check_equivalence(...))`; `parsed` separates "wrong" from
    "couldn't read it" for callers that care.
    """

    outcome: EquivalenceOutcome
    detail: str = ""

    @property
    def equivalent(self) -> bool:
        return self.outcome is EquivalenceOutcome.EQUIVALENT

    @property
    def parsed(self) -> bool:
        return self.outcome is not EquivalenceOutcome.PARSE_ERROR

    def __bool__(self) -> bool:
        return self.equivalent


class _ParseError(Exception):
    """Internal: raised by `_parse`, converted to a PARSE_ERROR result."""


def _parse(text: str, symbols: dict[str, sp.Symbol]) -> sp.Expr:
    if not isinstance(text, str) or not text.strip():
        raise _ParseError("empty expression")
    if len(text) > _MAX_EXPR_LEN:
        raise _ParseError(f"expression longer than {_MAX_EXPR_LEN} characters")
    if "__" in text:
        raise _ParseError("'__' is not allowed")
    if not _ALLOWED_CHARS.match(text):
        raise _ParseError("contains a character that isn't part of an expression")

    local_dict = dict(_ALLOWED_NAMES)
    local_dict.update(symbols)
    try:
        expr = parse_expr(
            text,
            local_dict=local_dict,
            transformations=_TRANSFORMS,
            evaluate=True,
        )
    except Exception as exc:  # SyntaxError, TokenError, TypeError, ...
        raise _ParseError(f"could not parse: {exc}") from exc

    if not isinstance(expr, sp.Expr):
        raise _ParseError("not a scalar expression")
    return expr


def _is_zero(expr: sp.Expr) -> bool:
    """True only when `expr` provably simplifies to 0."""
    simplified = sp.simplify(sp.expand(expr))
    if simplified == 0:
        return True
    # A second pass catches trig / log identities `expand` leaves alone.
    return sp.simplify(sp.trigsimp(simplified)) == 0


def check_equivalence(
    expr_a: str,
    expr_b: str,
    *,
    variables: Sequence[str] | None = None,
    domain: str = "real",
) -> EquivalenceResult:
    """Decide whether `expr_a` and `expr_b` denote the same expression.

    `variables` names the symbols that carry `domain`'s assumptions (e.g. `x`
    is real); any other name in either string is still parsed as a free symbol.
    `domain` is one of `"real"` (default), `"positive"`, `"complex"`.
    """
    if domain not in _DOMAIN_ASSUMPTIONS:
        raise ValueError(f"unknown domain: {domain!r}")

    assumptions = _DOMAIN_ASSUMPTIONS[domain]
    symbols = {
        name: sp.Symbol(name, **assumptions)
        for name in (variables or ())
        if isinstance(name, str) and name
    }

    try:
        parsed_a = _parse(expr_a, symbols)
        parsed_b = _parse(expr_b, symbols)
    except _ParseError as exc:
        return EquivalenceResult(EquivalenceOutcome.PARSE_ERROR, str(exc))

    try:
        if _is_zero(parsed_a - parsed_b):
            return EquivalenceResult(EquivalenceOutcome.EQUIVALENT)

        # `.equals` does a symbolic + randomized-numeric check that catches
        # cases `simplify` can't close; it returns None when undecided.
        verdict = parsed_a.equals(parsed_b)
        if verdict is True:
            return EquivalenceResult(EquivalenceOutcome.EQUIVALENT)
        if verdict is False:
            return EquivalenceResult(
                EquivalenceOutcome.NOT_EQUIVALENT, "expressions differ"
            )
        return EquivalenceResult(
            EquivalenceOutcome.NOT_EQUIVALENT, "equivalence undetermined"
        )
    except Exception as exc:  # a SymPy blow-up on parsed input is still "differ"
        return EquivalenceResult(
            EquivalenceOutcome.NOT_EQUIVALENT, f"comparison failed: {exc}"
        )
