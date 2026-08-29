"""`/practice/...` — starting a Topic practice session, submitting answers, and
requesting a worked solution.

Reached in the browser under `/api/practice/...` (the proxy strips `/api`).

Grading is entirely server-side (`app/practice/grading.py`); the correct answer
never reaches the browser. Every endpoint requires a verified caller. Students
can only practise `published` Topics; a `ContentAdmin` may also practise drafts
(for preview). Each submission writes a `QuestionAttempt`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_verified_user
from app.clock import Clock, get_clock
from app.content_access import topic_is_published
from app.database import get_db
from app.models import (
    Question,
    QuestionAttempt,
    Topic,
    User,
    is_content_admin,
)
from app.practice.grading import is_correct
from app.practice.payload import public_question
from app.practice.settings import solution_reveal_after_attempts
from app.schemas import (
    PracticeSessionOut,
    SolutionResponse,
    StartPracticeRequest,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
    TopicRef,
)

router = APIRouter(prefix="/practice", tags=["practice"])


def _not_found(what: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"No such {what}."
    )


def _visible_to(user: User, topic: Topic) -> bool:
    """A student practises only published Topics; a ContentAdmin also drafts."""
    return is_content_admin(user) or topic_is_published(topic)


def _visible_topic_or_404(db: Session, slug: str, user: User) -> Topic:
    topic = db.scalar(select(Topic).where(Topic.slug == slug))
    if topic is None or not _visible_to(user, topic):
        raise _not_found("topic")
    return topic


def _practisable_question_or_404(
    db: Session, question_id: int, user: User
) -> Question:
    question = db.get(Question, question_id)
    if question is None or not _visible_to(user, question.topic):
        raise _not_found("question")
    return question


@router.post("/sessions", response_model=PracticeSessionOut)
def start_session(
    body: StartPracticeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_verified_user),
) -> PracticeSessionOut:
    topic = _visible_topic_or_404(db, body.topic_slug, user)
    # `Question` has no `order` column (per the ticket schema); id order is
    # seed order, i.e. the order questions appear in the manifest.
    questions = list(
        db.scalars(
            select(Question)
            .where(Question.topic_id == topic.id)
            .order_by(Question.id)
        )
    )
    return PracticeSessionOut(
        topic=TopicRef.model_validate(topic),
        questions=[public_question(q) for q in questions],
    )


@router.post(
    "/questions/{question_id}/submit", response_model=SubmitAnswerResponse
)
def submit_answer(
    question_id: int,
    body: SubmitAnswerRequest,
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    user: User = Depends(require_verified_user),
) -> SubmitAnswerResponse:
    question = _practisable_question_or_404(db, question_id, user)
    correct = is_correct(question.type, question.answer_schema, body.answer)

    graded_so_far = db.scalar(
        select(func.count())
        .select_from(QuestionAttempt)
        .where(
            QuestionAttempt.user_id == user.id,
            QuestionAttempt.question_id == question.id,
            QuestionAttempt.attempt_no > 0,
        )
    )
    attempt_no = graded_so_far + 1

    db.add(
        QuestionAttempt(
            user_id=user.id,
            question_id=question.id,
            submitted_answer=body.answer,
            is_correct=correct,
            time_taken=body.time_taken,
            attempt_no=attempt_no,
            created_at=clock.now(),
        )
    )
    db.commit()

    reveal_after = solution_reveal_after_attempts(db)
    return SubmitAnswerResponse(
        is_correct=correct,
        attempt_no=attempt_no,
        worked_solution=(
            question.worked_solution
            if attempt_no >= reveal_after
            else None
        ),
    )


@router.post(
    "/questions/{question_id}/show-solution", response_model=SolutionResponse
)
def show_solution(
    question_id: int,
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    user: User = Depends(require_verified_user),
) -> SolutionResponse:
    # This is the explicit "show me the solution" request — it always returns
    # it. Only the automatic reveal in `submit` is gated by the
    # `solution_reveal_after_attempts` Setting.
    question = _practisable_question_or_404(db, question_id, user)

    latest = db.scalar(
        select(QuestionAttempt)
        .where(
            QuestionAttempt.user_id == user.id,
            QuestionAttempt.question_id == question.id,
        )
        .order_by(QuestionAttempt.id.desc())
    )
    if latest is None:
        # No submission yet — record a marker row so the view is still counted.
        db.add(
            QuestionAttempt(
                user_id=user.id,
                question_id=question.id,
                attempt_no=0,
                solution_viewed=True,
                created_at=clock.now(),
            )
        )
    else:
        latest.solution_viewed = True
    db.commit()

    return SolutionResponse(worked_solution=question.worked_solution)
