"""Unit tests for the pure CAS equivalence check (`app/cas/`).

Like the grader in `test_grading.py`, `check_equivalence` is a pure function —
no DB, no request, no fake — so it's tested directly. Three things to pin down:
pairs that *are* equivalent (including ones a string compare would miss), pairs
that are *not*, and malformed input (which must resolve, never raise).
"""

from __future__ import annotations

import dataclasses

import pytest

from app.cas import EquivalenceOutcome, EquivalenceResult, check_equivalence


# -- equivalent pairs -------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("2(x+1)", "2x+2"),               # implicit multiplication + expand
        ("2*(x+1)", "2*x + 2"),
        ("x + y", "y + x"),               # commutativity / rearrangement
        ("3(a - b)", "3a - 3b"),
        ("(x+1)**2", "x^2 + 2x + 1"),     # ^ as power, binomial expansion
        ("(x + 1)*(x - 1)", "x**2 - 1"),
        ("1/2 x", "0.5*x"),               # rational vs decimal coefficient
        ("x/x", "1"),
        ("(x**2 - 1)/(x - 1)", "x + 1"),  # cancels
        ("sin(x)**2 + cos(x)**2", "1"),   # in-scope trig identity
        ("ln(exp(x))", "x"),
        ("2x - x", "x"),
    ],
)
def test_equivalent_pairs_match(a, b):
    result = check_equivalence(a, b, variables=["x", "y", "a", "b"])
    assert result.outcome is EquivalenceOutcome.EQUIVALENT
    assert result.equivalent is True
    assert result.parsed is True
    assert bool(result) is True


def test_equivalence_is_symmetric():
    assert check_equivalence("2x + 2", "2(x + 1)", variables=["x"]).equivalent
    assert check_equivalence("2(x + 1)", "2x + 2", variables=["x"]).equivalent


def test_domain_assumptions_change_the_verdict():
    # sqrt(x**2) == x only once x is known non-negative.
    assert not check_equivalence(
        "sqrt(x**2)", "x", variables=["x"], domain="real"
    ).equivalent
    assert check_equivalence(
        "sqrt(x**2)", "x", variables=["x"], domain="positive"
    ).equivalent
    # complex leaves the fewest assumptions on x; still not equivalent, and the
    # domain still round-trips a plain algebraic identity.
    assert not check_equivalence(
        "sqrt(x**2)", "x", variables=["x"], domain="complex"
    ).equivalent
    assert check_equivalence(
        "(x + 1)**2", "x**2 + 2x + 1", variables=["x"], domain="complex"
    ).equivalent


# -- non-equivalent pairs -------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("2x + 3", "2x + 4"),
        ("x*y", "x + y"),
        ("(x + 1)**2", "x**2 + 1"),
        ("2x", "x"),
        ("sin(x)", "cos(x)"),
        ("x**2", "x**3"),
        ("1/x", "x"),
    ],
)
def test_non_equivalent_pairs_do_not_match(a, b):
    result = check_equivalence(a, b, variables=["x", "y"])
    assert result.outcome is EquivalenceOutcome.NOT_EQUIVALENT
    assert result.equivalent is False
    assert result.parsed is True          # it parsed — it's just wrong
    assert bool(result) is False


# -- malformed / unparseable input --------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "",                      # empty
        "   ",                   # whitespace only
        "2x +",                  # dangling operator
        "2x + )",                # unbalanced paren
        "x = 3",                 # an equation, not an expression
        "x!",                    # unsupported token
        "[1, 2, 3]",             # not a scalar expression
        "__import__('os')",      # dunder — rejected before the parser
        "().__class__",
        "x" + "*" * 600,         # over the length cap
    ],
)
def test_unparseable_input_reports_parse_error_and_never_raises(bad):
    result = check_equivalence(bad, "x", variables=["x"])
    assert result.outcome is EquivalenceOutcome.PARSE_ERROR
    assert result.parsed is False
    assert result.equivalent is False
    assert bool(result) is False
    assert result.detail                    # a reason is always given


def test_parse_error_on_the_second_operand_too():
    assert (
        check_equivalence("x", "still bad )", variables=["x"]).outcome
        is EquivalenceOutcome.PARSE_ERROR
    )


@pytest.mark.parametrize("junk", ["x y z", "2 2", "2..3", "1 2 3"])
def test_whitespace_separated_junk_resolves_without_raising(junk):
    # The char whitelist lets these through and implicit multiplication makes
    # them parse (`x y z` -> `x*y*z`); the contract only promises a definite
    # result, and a wrong one is definite.
    result = check_equivalence(junk, "x", variables=["x"])
    assert result.outcome in (
        EquivalenceOutcome.NOT_EQUIVALENT,
        EquivalenceOutcome.PARSE_ERROR,
    )


def test_non_string_input_is_a_parse_error_not_a_crash():
    assert check_equivalence(None, "x").outcome is EquivalenceOutcome.PARSE_ERROR  # type: ignore[arg-type]
    assert check_equivalence("x", 5).outcome is EquivalenceOutcome.PARSE_ERROR  # type: ignore[arg-type]


# -- guard rails --------------------------------------------------------


def test_unknown_domain_raises():
    # `domain` is caller config, not student input — a bad value is a bug,
    # handled the way `grading.is_correct` handles an unknown question type.
    with pytest.raises(ValueError):
        check_equivalence("x", "x", variables=["x"], domain="quaternion")


def test_variables_argument_is_optional():
    assert check_equivalence("1 + 1", "2").equivalent
    assert check_equivalence("a + a", "2*a").equivalent  # free symbol, no list


def test_result_is_frozen():
    result = check_equivalence("x", "x", variables=["x"])
    assert isinstance(result, EquivalenceResult)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.outcome = EquivalenceOutcome.NOT_EQUIVALENT  # type: ignore[misc]
