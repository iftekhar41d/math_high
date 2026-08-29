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
    QUESTION_MULTI_PART,
    QUESTION_NUMERIC,
    QUESTION_SYMBOLIC,
)
from app.practice.grading import (
    correct_answer_text,
    grade_parts,
    is_correct,
)


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


# -- symbolic --------------------------------------------------------------


def _sym_schema(expr="2*x + 2", **extra):
    return {"expression": expr, "variables": ["x"], **extra}


def test_symbolic_accepts_any_mathematically_equivalent_expression():
    schema = _sym_schema("2*x + 2")
    assert is_correct(QUESTION_SYMBOLIC, schema, "2x + 2") is True
    assert is_correct(QUESTION_SYMBOLIC, schema, "2*(x + 1)") is True
    assert is_correct(QUESTION_SYMBOLIC, schema, "x + 2 + x") is True


def test_symbolic_rejects_a_different_expression():
    schema = _sym_schema("2*x + 2")
    assert is_correct(QUESTION_SYMBOLIC, schema, "2*x + 3") is False
    assert is_correct(QUESTION_SYMBOLIC, schema, "2*x") is False


def test_symbolic_malformed_submission_grades_false_never_raises():
    schema = _sym_schema("2*x + 2")
    assert is_correct(QUESTION_SYMBOLIC, schema, "2x +* ") is False  # junk
    assert is_correct(QUESTION_SYMBOLIC, schema, "") is False
    assert is_correct(QUESTION_SYMBOLIC, schema, None) is False
    assert is_correct(QUESTION_SYMBOLIC, schema, 4) is False  # not a string
    assert is_correct(QUESTION_SYMBOLIC, schema, ["2x + 2"]) is False


def test_symbolic_honours_the_domain():
    # sqrt(x**2) == x only when x is known non-negative.
    real = {"expression": "sqrt(x**2)", "variables": ["x"], "domain": "real"}
    positive = {**real, "domain": "positive"}
    assert is_correct(QUESTION_SYMBOLIC, real, "x") is False
    assert is_correct(QUESTION_SYMBOLIC, positive, "x") is True


def test_symbolic_unknown_domain_raises_like_an_unknown_type():
    with pytest.raises(ValueError):
        is_correct(
            QUESTION_SYMBOLIC,
            {"expression": "x", "variables": ["x"], "domain": "quaternion"},
            "x",
        )


# -- multi_part ----------------------------------------------------------


def _mp_schema():
    return {
        "parts": [
            {"id": "a", "type": "numeric", "answer_schema": {"value": 3}},
            {
                "id": "b",
                "type": "mcq_single",
                "answer_schema": {
                    "options": [
                        {"id": "x", "text": "ex"},
                        {"id": "y", "text": "why"},
                    ],
                    "correct_option": "y",
                },
            },
            {
                "id": "c",
                "type": "symbolic",
                "answer_schema": {"expression": "x + 1", "variables": ["x"]},
            },
        ]
    }


def test_multi_part_correct_only_when_all_parts_are():
    schema = _mp_schema()
    assert (
        is_correct(
            QUESTION_MULTI_PART,
            schema,
            {"a": 3, "b": "y", "c": "1 + x"},
        )
        is True
    )
    assert (
        is_correct(
            QUESTION_MULTI_PART,
            schema,
            {"a": 3, "b": "x", "c": "1 + x"},  # b wrong
        )
        is False
    )


def test_grade_parts_returns_the_per_part_vector_in_order():
    schema = _mp_schema()
    assert grade_parts(schema, {"a": 3, "b": "y", "c": "x + 1"}) == [
        True,
        True,
        True,
    ]
    assert grade_parts(schema, {"a": 99, "b": "y", "c": "nope"}) == [
        False,
        True,
        False,
    ]


def test_grade_parts_treats_a_non_mapping_or_missing_part_as_wrong():
    schema = _mp_schema()
    assert grade_parts(schema, None) == [False, False, False]
    assert grade_parts(schema, "not a dict") == [False, False, False]
    assert grade_parts(schema, {"a": 3}) == [True, False, False]


def test_multi_part_with_no_parts_is_not_correct():
    assert is_correct(QUESTION_MULTI_PART, {"parts": []}, {}) is False
    assert grade_parts({"parts": []}, {}) == []


# -- guard rails ---------------------------------------------------------


def test_unknown_question_type_raises():
    with pytest.raises(ValueError):
        is_correct("essay", {}, "anything")


# -- correct_answer_text (MentisQ context) -----------------------------------


def test_correct_answer_text_renders_each_type():
    single = {
        "options": [{"id": "a", "text": "-8"}, {"id": "b", "text": "2"}],
        "correct_option": "b",
    }
    assert correct_answer_text(QUESTION_MCQ_SINGLE, single) == "b) 2"

    multi = {
        "options": [
            {"id": "a", "text": "-4"},
            {"id": "b", "text": "0"},
            {"id": "c", "text": "-1"},
        ],
        "correct_options": ["a", "c"],
    }
    assert correct_answer_text(QUESTION_MCQ_MULTI, multi) == "a) -4, c) -1"

    assert (
        correct_answer_text(QUESTION_NUMERIC, {"value": 1.71, "tolerance": 0.01})
        == "1.71 (± 0.01)"
    )
    assert correct_answer_text(QUESTION_NUMERIC, {"value": 7}) == "7"

    assert (
        correct_answer_text(QUESTION_SYMBOLIC, _sym_schema("2*x + 2"))
        == "2*x + 2"
    )
    assert correct_answer_text(QUESTION_MULTI_PART, _mp_schema()) == (
        "a) 3; b) y) why; c) x + 1"
    )


def test_correct_answer_text_unknown_type_raises():
    with pytest.raises(ValueError):
        correct_answer_text("essay", {})
