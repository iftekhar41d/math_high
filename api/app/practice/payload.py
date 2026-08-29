"""The student-facing view of a `Question`.

This is the single chokepoint between the stored question (whose `answer_schema`
always contains the correct answer) and the browser. It copies across only the
body, difficulty, and — for MCQs — the option ids and text. The
`correct_option` / `correct_options` / `value` / `tolerance` keys never pass
through here.
"""

from __future__ import annotations

from app.models import QUESTION_MCQ_MULTI, QUESTION_MCQ_SINGLE, Question
from app.schemas import PracticeQuestionOut, QuestionOptionOut

_MCQ_TYPES = {QUESTION_MCQ_SINGLE, QUESTION_MCQ_MULTI}


def public_question(question: Question) -> PracticeQuestionOut:
    options: list[QuestionOptionOut] | None = None
    if question.type in _MCQ_TYPES:
        options = [
            QuestionOptionOut(id=str(o["id"]), text=str(o["text"]))
            for o in question.answer_schema.get("options", [])
        ]
    return PracticeQuestionOut(
        id=question.id,
        type=question.type,
        difficulty=question.difficulty,
        body=question.body,
        options=options,
    )
