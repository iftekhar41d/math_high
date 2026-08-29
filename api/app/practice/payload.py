"""The student-facing view of a `Question`.

This is the single chokepoint between the stored question (whose `answer_schema`
always contains the correct answer) and the browser. It copies across only the
body, difficulty, and — for MCQs — the option ids and text. The
`correct_option` / `correct_options` / `value` / `tolerance` / `expression` keys
never pass through here. For a `multi_part` question it recurses into every
part, applying the same stripping.
"""

from __future__ import annotations

from typing import Any

from app.models import (
    QUESTION_MCQ_MULTI,
    QUESTION_MCQ_SINGLE,
    QUESTION_MULTI_PART,
    Question,
)
from app.schemas import PracticePartOut, PracticeQuestionOut, QuestionOptionOut

_MCQ_TYPES = {QUESTION_MCQ_SINGLE, QUESTION_MCQ_MULTI}


def _options(schema: dict[str, Any]) -> list[QuestionOptionOut]:
    return [
        QuestionOptionOut(id=str(o["id"]), text=str(o["text"]))
        for o in schema.get("options", [])
    ]


def _public_part(part: dict[str, Any]) -> PracticePartOut:
    part_type = part.get("type", "")
    part_schema = part.get("answer_schema") or {}
    body = part.get("body")
    return PracticePartOut(
        id=str(part.get("id", "")),
        type=part_type,
        body=str(body) if body is not None else None,
        options=_options(part_schema) if part_type in _MCQ_TYPES else None,
    )


def public_question(question: Question) -> PracticeQuestionOut:
    options: list[QuestionOptionOut] | None = None
    parts: list[PracticePartOut] | None = None

    if question.type in _MCQ_TYPES:
        options = _options(question.answer_schema)
    elif question.type == QUESTION_MULTI_PART:
        parts = [
            _public_part(p)
            for p in question.answer_schema.get("parts", [])
        ]

    return PracticeQuestionOut(
        id=question.id,
        type=question.type,
        difficulty=question.difficulty,
        body=question.body,
        options=options,
        parts=parts,
    )
