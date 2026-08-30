"""Unit tests for the pure MentisQ step-check (`app/mentisq/step_check.py`).

Like `test_cas.py`, `check_working` is a pure, total function — no DB, no
request, no fake — so it is tested directly. It either returns a verdict block
(`- step N: VALID` / `- step N: INVALID — …` under a "reference only" header) or
`None` when the turn holds nothing it can check.
"""

from __future__ import annotations

import pytest

from app.mentisq.step_check import check_working

HEADER_MARK = "Automated algebra check"


# -- nothing to check → None ---------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "I'm really stuck, can you explain how to start?",
        "What is the derivative of x squared?",
        "is the answer = 4?",  # "answer" is prose → chain disqualified
        "so then x plus one = two x",  # all prose members
        "2x + 4 = 10",  # a lone conditional equation, not an identity claim
        "x = x",  # trivial, still a lone equality
    ],
)
def test_returns_none_when_there_is_nothing_checkable(text):
    assert check_working(text) is None


# -- a multi-line simplification chain ---------------------------------------


def test_valid_continuation_chain_is_reported_valid():
    block = check_working("3(x + 2)\n= 3x + 6")
    assert block is not None
    assert HEADER_MARK in block
    assert "- step 2: VALID" in block
    assert "- step 2: INVALID" not in block


def test_invalid_continuation_step_is_flagged_with_both_sides():
    block = check_working("3(x + 2)\n= 3x + 5")
    assert block is not None
    assert "- step 2: INVALID" in block
    assert "3(x + 2)" in block and "3x + 5" in block


def test_three_member_chain_numbers_each_step():
    # step 2 is wrong (dropped the +2), step 3 recovers from the wrong line.
    block = check_working("3(x + 2) - 4\n= 3x - 4\n= 3x - 4")
    assert "- step 2: INVALID" in block
    assert "- step 3: VALID" in block


def test_single_line_equality_chain_is_checked():
    # `a = b = c` on one line is an asserted chain of equalities, not an
    # equation being solved — three members, so it is checked.
    block = check_working("2(x + 1) = 2x + 2 = 2x + 1")
    assert "- step 2: VALID" in block
    assert "- step 3: INVALID" in block


def test_list_and_step_prefixes_are_stripped():
    block = check_working("1) 3(x + 2)\n= 3x + 6")
    assert block is not None and "- step 2: VALID" in block

    bulleted = check_working("- 3(x + 2)\n- = 3x + 5")
    assert bulleted is not None and "- step 2: INVALID" in bulleted


def test_leading_minus_is_not_treated_as_a_bullet():
    # "-3(x-2)" must stay negative, so this remains a lone equality → None.
    assert check_working("-3(x - 2) = -3x + 6") is None


# -- a multi-line equation chain (`L = R` per line) -------------------------


def test_equation_chain_sound_additive_step_is_reported_valid():
    # 2x + 4 = 10  →  2x = 6 subtracts 4 from both sides: (2x + 4) - 10 and
    # 2x - 6 are the same, so the step is provably sound.
    block = check_working("2x + 4 = 10\n2x = 6\nx = 3")
    assert block is not None
    assert HEADER_MARK in block
    assert "- step 2: VALID" in block
    assert "- step 2: INVALID" not in block


def test_equation_chain_division_step_is_left_silent_not_invalid():
    # 2x = 6  →  x = 3 divides both sides by 2. (2x - 6) and (x - 3) are not
    # equivalent, but the step is legal — app.cas can't tell it from an error,
    # so nothing is emitted for step 3 (and never INVALID).
    block = check_working("2x + 4 = 10\n2x = 6\nx = 3")
    assert "step 3" not in block


def test_equation_chain_rearrangement_step_is_reported_valid():
    block = check_working("x + 3 = 2x\n3 = 2x - x\nx = 3")
    assert block is not None and "- step 2: VALID" in block


def test_broken_additive_equation_step_stays_silent():
    # 2x + 4 = 10  →  2x = 7 is wrong (should be 6), but an equation chain never
    # emits INVALID: a false "not equivalent" here is indistinguishable to
    # app.cas from a legitimate multiplicative move.
    assert check_working("2x + 4 = 10\n2x = 7") is None


def test_equation_chain_never_emits_invalid():
    for text in [
        "3x + 6 = 12\n3x = 5",
        "5x - 2 = 8\n5x = 9\nx = 2",
        "x/2 + 1 = 4\nx = 5",
    ]:
        block = check_working(text)
        assert block is None or "step 2: INVALID" not in block


def test_equation_chain_with_an_unparseable_line_is_silent_for_that_step():
    # The only step's second equation can't be parsed → nothing injected.
    assert check_working("x + 1 = y + 1\nx = (y") is None
    # A sound step 2, then an unparseable step 3 → step 2 stands, step 3 silent.
    block = check_working("3x + 6 = 12\n3x = 6\nx = (2")
    assert block is not None and "- step 2: VALID" in block
    assert "step 3" not in block


def test_a_lone_equation_line_still_injects_nothing():
    # A run needs 2+ consecutive `L = R` lines; one on its own is a conditional
    # equation being solved, not a claim to check.
    assert check_working("3(x + 2) = 3x + 6\n\nsome prose here") is None


# -- robustness ------------------------------------------------------------------


def test_restricted_domain_identity_is_passed_over_not_flagged():
    # `sqrt(x^2) = x` is false for real x in general but true for x > 0. The
    # check only calls a step INVALID when it fails under every domain, so this
    # is left silent rather than misreported.
    block = check_working("sqrt(x^2)\n= x")
    assert block is None or "- step 2: INVALID" not in block


def test_unparseable_member_in_a_chain_is_silent_not_invalid():
    # The second line can't be read as an expression; it is skipped, not
    # reported as a wrong step.
    block = check_working("x + 1\n= (x +")
    assert block is None or "- step" not in block


def test_never_raises_on_odd_input():
    for text in ["=", "==", "= = =", "x =\n= y", "((((", "1/0 = 1", "^^ = ^^"]:
        check_working(text)  # must not raise


def test_step_count_is_bounded():
    chain = "x\n" + "\n".join("= x" for _ in range(60))
    block = check_working(chain)
    assert block is not None
    assert block.count("- step") <= 20


def test_equation_run_step_count_is_bounded():
    # A long run of sound additive steps (each adds 1 to both sides) still caps
    # the emitted verdicts, and an equally long all-silent run stays bounded
    # without emitting anything.
    sound = "\n".join(f"x + {n} = {n}" for n in range(60))
    block = check_working(sound)
    assert block is not None and block.count("- step") <= 20
    silent = "\n".join(f"{2 ** n}*x = {2 ** n}" for n in range(30))
    assert check_working(silent) is None
