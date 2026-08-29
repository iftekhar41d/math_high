"""`/dashboard` — the signed-in student's recent activity.

Reached in the browser under `/api/dashboard` (the proxy strips `/api`).

One endpoint: `GET /dashboard` returns three views of the caller's own data,
all computed on read — there is no snapshot table and no recompute job:

- ``recent_attempts`` — the student's graded attempts (``attempt_no > 0``),
  newest first, capped at ``RECENT_ATTEMPTS_LIMIT``. Solution-only marker rows
  (``attempt_no = 0``) are excluded.
- ``topic_performance`` — one row per Topic the student has a graded attempt in;
  ``percent_correct`` is correct graded attempts / graded attempts x 100,
  rounded to one decimal. Ordered by Topic title.
- ``activity`` — counts over the last ``ACTIVITY_WINDOW_DAYS`` days, by the
  injected ``Clock``: ``TopicView`` rows, the distinct Topics behind them, and
  the student's ``ok`` MentisQ user turns.

Every call requires a verified caller.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_verified_user
from app.clock import Clock, get_clock
from app.database import get_db
from app.models import (
    MENTISQ_ROLE_USER,
    MENTISQ_STATUS_OK,
    MentisQMessage,
    MentisQSession,
    Question,
    QuestionAttempt,
    Topic,
    TopicView,
    User,
)
from app.schemas import (
    DashboardActivityOut,
    DashboardAttemptOut,
    StudentDashboardOut,
    TopicPerformanceOut,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Newest N graded submissions returned in `recent_attempts`.
RECENT_ATTEMPTS_LIMIT = 20
# `activity` counts events from the last this-many days.
ACTIVITY_WINDOW_DAYS = 30


@router.get("", response_model=StudentDashboardOut)
def get_dashboard(
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    user: User = Depends(require_verified_user),
) -> StudentDashboardOut:
    return StudentDashboardOut(
        recent_attempts=_recent_attempts(db, user.id),
        topic_performance=_topic_performance(db, user.id),
        activity=_activity(db, user.id, clock),
    )


def _recent_attempts(db: Session, user_id: int) -> list[DashboardAttemptOut]:
    rows = db.execute(
        select(
            QuestionAttempt.id,
            QuestionAttempt.question_id,
            Topic.slug,
            Topic.title,
            Question.difficulty,
            QuestionAttempt.is_correct,
            QuestionAttempt.attempt_no,
            QuestionAttempt.time_taken,
            QuestionAttempt.solution_viewed,
            QuestionAttempt.created_at,
        )
        .join(Question, Question.id == QuestionAttempt.question_id)
        .join(Topic, Topic.id == Question.topic_id)
        .where(
            QuestionAttempt.user_id == user_id,
            QuestionAttempt.attempt_no > 0,
        )
        .order_by(
            QuestionAttempt.created_at.desc(), QuestionAttempt.id.desc()
        )
        .limit(RECENT_ATTEMPTS_LIMIT)
    ).all()
    return [
        DashboardAttemptOut(
            id=r.id,
            question_id=r.question_id,
            topic_slug=r.slug,
            topic_title=r.title,
            difficulty=r.difficulty,
            is_correct=bool(r.is_correct),
            attempt_no=r.attempt_no,
            time_taken=r.time_taken,
            solution_viewed=r.solution_viewed,
            created_at=r.created_at,
        )
        for r in rows
    ]


def _topic_performance(
    db: Session, user_id: int
) -> list[TopicPerformanceOut]:
    rows = db.execute(
        select(
            Topic.slug,
            Topic.title,
            func.count().label("attempts"),
            func.sum(
                case((QuestionAttempt.is_correct.is_(True), 1), else_=0)
            ).label("correct"),
        )
        .select_from(QuestionAttempt)
        .join(Question, Question.id == QuestionAttempt.question_id)
        .join(Topic, Topic.id == Question.topic_id)
        .where(
            QuestionAttempt.user_id == user_id,
            QuestionAttempt.attempt_no > 0,
        )
        .group_by(Topic.id, Topic.slug, Topic.title)
        .order_by(Topic.title)
    ).all()
    return [
        TopicPerformanceOut(
            topic_slug=r.slug,
            topic_title=r.title,
            attempts=r.attempts,
            correct=r.correct,
            percent_correct=round(r.correct / r.attempts * 100, 1),
        )
        for r in rows
    ]


def _activity(
    db: Session, user_id: int, clock: Clock
) -> DashboardActivityOut:
    window_start = clock.now() - timedelta(days=ACTIVITY_WINDOW_DAYS)

    views = db.execute(
        select(
            func.count().label("total"),
            func.count(func.distinct(TopicView.topic_id)).label("distinct"),
        ).where(
            TopicView.user_id == user_id,
            TopicView.created_at >= window_start,
        )
    ).one()
    mentisq_messages = db.scalar(
        select(func.count())
        .select_from(MentisQMessage)
        .join(MentisQSession)
        .where(
            MentisQSession.user_id == user_id,
            MentisQMessage.role == MENTISQ_ROLE_USER,
            MentisQMessage.status == MENTISQ_STATUS_OK,
            MentisQMessage.created_at >= window_start,
        )
    )
    return DashboardActivityOut(
        window_days=ACTIVITY_WINDOW_DAYS,
        topic_views=views.total,
        topics_viewed=views.distinct,
        mentisq_messages=mentisq_messages,
    )
