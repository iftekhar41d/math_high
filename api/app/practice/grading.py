"""Server-side grading — the only place a student's answer is checked.

Pure functions over a question's `type` + `answer_schema` + the submitted
answer. No DB, no request context; the router persists the result.
"""

from __future__ import annotations

import math
from typing import Any

from app.models import (
    QUESTION_MCQ_MULTI,
    QUESTION_MCQ_SINGLE,
    QUESTION_NUMERIC,
)


def is_correct(
    question_type: str, answer_schema: dict[str, Any], submitted: Any
) -> bool:
    """Grade `submitted` against `answer_schema` for a question of
    `question_type`. Any malformed submission grades as incorrect (never an
    error); an unknown `question_type` is a programming error and raises.
    """
    if question_type == QUESTION_MCQ_SINGLE:
        return submitted == answer_schema.get("correct_option")

    if question_type == QUESTION_MCQ_MULTI:
        if not isinstance(submitted, (list, tuple)):
            return False
        return set(submitted) == set(answer_schema.get("correct_options", []))

    if question_type == QUESTION_NUMERIC:
        if isinstance(submitted, (bool, list, dict)):
            return False
        try:
            value = float(submitted)
        except (TypeError, ValueError):
            return False
        target = float(answer_schema["value"])
        tolerance = float(answer_schema.get("tolerance") or 0)
        difference = abs(value - target)
        # `<=` alone rejects answers that land exactly on the tolerance edge
        # when the arithmetic isn't exactly representable (e.g. target 1.71,
        # tolerance 0.01, answer 1.72), so treat an edge case as inside.
        return difference <= tolerance or math.isclose(
            difference, tolerance, rel_tol=1e-9, abs_tol=1e-12
        )

    raise ValueError(f"unknown question type: {question_type!r}")


def correct_answer_text(
    question_type: str, answer_schema: dict[str, Any]
) -> str:
    """A short human-readable rendering of the correct answer, for MentisQ's
    system prompt (it is never shown to the student). Lives here because this is
    the module that already knows the `answer_schema` shape per type.
    """
    options = {
        str(o["id"]): str(o["text"])
        for o in answer_schema.get("options", [])
    }

    if question_type == QUESTION_MCQ_SINGLE:
        cid = str(answer_schema.get("correct_option", ""))
        return f"{cid}) {options.get(cid, '')}".strip()

    if question_type == QUESTION_MCQ_MULTI:
        cids = [str(c) for c in answer_schema.get("correct_options", [])]
        return ", ".join(
            f"{c}) {options.get(c, '')}".strip() for c in cids
        )

    if question_type == QUESTION_NUMERIC:
        value = answer_schema.get("value")
        tolerance = answer_schema.get("tolerance")
        if tolerance:
            return f"{value} (± {tolerance})"
        return f"{value}"

    raise ValueError(f"unknown question type: {question_type!r}")
