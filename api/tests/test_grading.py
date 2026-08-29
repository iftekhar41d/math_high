"""Unit tests for the pure server-side grader (`app/practice/grading.py`).

The grader is a pure function — no DB, no request — so it's tested directly.
Everything else in the practice slice is exercised through the HTTP API in
`test_practice.py`.
"""

from __future__ import annotations

import pytest

from app.models import (
    QUESTION_MCQ_MULTI,
    QUESTION_MCQ_SINGLE,
    QUESTION_NUMERIC,
)
from app.practice.grading import is_correct


# -- mcq_single ---------------------------------------------------------------


def test_mcq_single_matches_the_one_correct_option():
    schema = {"options": [{"id": "a"}, {"id": "b"}], "correct_option": "b"}
    assert is_correct(QUESTION_MCQ_SINGLE, schema, "b") is True
    assert is_correct(QUESTION_MCQ_SINGLE, schema, "a") is False


def test_mcq_single_rejects_a_list_or_missing_answer():
    schema = {"correct_option": "b"}
    assert is_correct(QUESTION_MCQ_SINGLE, schema, ["b"]) is False
    assert is_correct(QUESTION_MCQ_SINGLE, schema, None) is False


# -- mcq_multi --------------------------------------------------------------


def test_mcq_multi_needs_the_exact_set_of_correct_options():
    schema = {"correct_options": ["a", "c"]}
    assert is_correct(QUESTION_MCQ_MULTI, schema, ["a", "c"]) is True
    assert is_correct(QUESTION_MCQ_MULTI, schema, ["c", "a"]) is True  # order-free


def test_mcq_multi_rejects_subset_superset_and_non_list():
    schema = {"correct_options": ["a", "c"]}
    assert is_correct(QUESTION_MCQ_MULTI, schema, ["a"]) is False
    assert is_correct(QUESTION_MCQ_MULTI, schema, ["a", "c", "d"]) is False
    assert is_correct(QUESTION_MCQ_MULTI, schema, "a") is False
    assert is_correct(QUESTION_MCQ_MULTI, schema, None) is False


# -- numeric ---------------------------------------------------------------


def test_numeric_accepts_values_within_tolerance_on_both_sides():
    schema = {"value": 10.0, "tolerance": 0.5}
    assert is_correct(QUESTION_NUMERIC, schema, 10.0) is True
    assert is_correct(QUESTION_NUMERIC, schema, 10.5) is True
    assert is_correct(QUESTION_NUMERIC, schema, 9.5) is True
    assert is_correct(QUESTION_NUMERIC, schema, "10.4") is True  # string coerced


def test_numeric_rejects_values_just_outside_tolerance():
    schema = {"value": 10.0, "tolerance": 0.5}
    assert is_correct(QUESTION_NUMERIC, schema, 10.51) is False
    assert is_correct(QUESTION_NUMERIC, schema, 9.49) is False


def test_numeric_edge_accepts_answers_on_a_non_representable_boundary():
    # 1.71 + 0.01 isn't exactly 1.72 in binary float; the student still lands
    # on the edge and should be marked correct.
    schema = {"value": 1.71, "tolerance": 0.01}
    assert is_correct(QUESTION_NUMERIC, schema, 1.72) is True
    assert is_correct(QUESTION_NUMERIC, schema, 1.70) is True
    assert is_correct(QUESTION_NUMERIC, schema, 1.7201) is False


def test_numeric_with_no_tolerance_demands_an_exact_match():
    schema = {"value": 7.0}
    assert is_correct(QUESTION_NUMERIC, schema, 7.0) is True
    assert is_correct(QUESTION_NUMERIC, schema, 7.01) is False


def test_numeric_rejects_non_numeric_input():
    schema = {"value": 7.0, "tolerance": 0.1}
    assert is_correct(QUESTION_NUMERIC, schema, "not a number") is False
    assert is_correct(QUESTION_NUMERIC, schema, None) is False
    assert is_correct(QUESTION_NUMERIC, schema, ["7"]) is False


# -- guard rails ---------------------------------------------------------


def test_unknown_question_type_raises():
    with pytest.raises(ValueError):
        is_correct("essay", {}, "anything")
