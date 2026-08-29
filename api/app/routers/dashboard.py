"""`/dashboard` — the signed-in student's recent activity.

Reached in the browser under `/api/dashboard` (the proxy strips `/api`).

One endpoint: `GET /dashboard` returns several views of the caller's own data.
Some are computed live on read; three read the cached `PerformanceSnapshot`
rows the out-of-band recompute job maintains (ticket 02):

- ``recent_attempts`` — the student's graded attempts (``attempt_no > 0``),
  newest first, capped at ``RECENT_ATTEMPTS_LIMIT``. Solution-only marker rows
  (``attempt_no = 0``) are excluded. Live.
- ``topic_performance`` — one row per Topic the student has a graded attempt in;
  ``percent_correct`` is correct graded attempts / graded attempts x 100,
  rounded to one decimal. Ordered by Topic title. Live, unchanged from Phase 1.
- ``skill_mastery`` — one row per SkillTag the student has a snapshot for, its
  cached mastery and an ``insufficient_data`` flag for the ``< 3`` sample case.
  Cached.
- ``topic_trends`` — the cached ``up`` / ``flat`` / ``down`` direction per Topic
  the student has a snapshot for, in syllabus order. Cached.
- ``recommendations`` — up to ``analytics.recommendation_count`` "study this
  next" Topics below ``analytics.mastery_threshold`` whose prerequisites are in
  order, weakest first; a prerequisite scoring lower still stands in for its
  Topic (see ``app.analytics.recommendations``). Cached.
- ``activity`` — counts over the last ``ACTIVITY_WINDOW_DAYS`` days, by the
  injected ``Clock``: ``TopicView`` rows, the distinct Topics behind them, and
  the student's ``ok`` MentisQ user turns. Live.

Every call requires a verified caller.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from app.analytics.recommendations import TopicNode, recommend
from app.analytics.settings import AnalyticsSettings
from app.auth.dependencies import require_verified_user
from app.clock import Clock, get_clock
from app.content_access import topic_is_published
from app.database import get_db
from app.models import (
    MENTISQ_ROLE_USER,
    MENTISQ_STATUS_OK,
    SNAPSHOT_DIMENSION_SKILL_TAG,
    SNAPSHOT_DIMENSION_TOPIC,
    SNAPSHOT_MIN_CONFIDENT_SAMPLE,
    MentisQMessage,
    MentisQSession,
    PerformanceSnapshot,
    Question,
    QuestionAttempt,
    SkillTag,
    Subject,
    Topic,
    TopicView,
    Unit,
    User,
)
from app.schemas import (
    DashboardActivityOut,
    DashboardAttemptOut,
    RecommendationOut,
    SkillMasteryOut,
    StudentDashboardOut,
    TopicPerformanceOut,
    TopicTrendOut,
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
    published = _published_topics(db)
    topic_snapshots = _topic_snapshots(db, user.id)
    return StudentDashboardOut(
        recent_attempts=_recent_attempts(db, user.id),
        topic_performance=_topic_performance(db, user.id),
        skill_mastery=_skill_mastery(db, user.id),
        topic_trends=_topic_trends(published, topic_snapshots),
        recommendations=_recommendations(db, published, topic_snapshots),
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


def _published_topics(db: Session) -> list[Topic]:
    """Every `published` Topic in syllabus order (Subject -> Unit -> Topic
    `order`), lecture content and prerequisites eager-loaded. Visibility is the
    shared `topic_is_published` rule (a student never sees a draft Topic, so it
    never reaches a trend row or a recommendation); draft prerequisites are
    dropped by the caller against this same published set."""
    topics = db.scalars(
        select(Topic)
        .join(Unit, Unit.id == Topic.unit_id)
        .join(Subject, Subject.id == Unit.subject_id)
        .order_by(Subject.order, Unit.order, Topic.order)
        .options(
            selectinload(Topic.lecture_content),
            selectinload(Topic.prerequisites),
        )
    )
    # A prerequisite counts as visible iff it is itself in this published set —
    # the caller filters `Topic.prerequisites` against it, so their lecture
    # content need not be loaded here.
    return [t for t in topics if topic_is_published(t)]


def _topic_snapshots(
    db: Session, user_id: int
) -> dict[int, PerformanceSnapshot]:
    rows = db.scalars(
        select(PerformanceSnapshot).where(
            PerformanceSnapshot.user_id == user_id,
            PerformanceSnapshot.dimension == SNAPSHOT_DIMENSION_TOPIC,
        )
    )
    return {row.dimension_id: row for row in rows}


def _skill_mastery(db: Session, user_id: int) -> list[SkillMasteryOut]:
    rows = db.execute(
        select(
            SkillTag.id,
            SkillTag.name,
            PerformanceSnapshot.mastery,
            PerformanceSnapshot.sample_size,
        )
        .join(
            PerformanceSnapshot,
            PerformanceSnapshot.dimension_id == SkillTag.id,
        )
        .where(
            PerformanceSnapshot.user_id == user_id,
            PerformanceSnapshot.dimension == SNAPSHOT_DIMENSION_SKILL_TAG,
        )
        .order_by(SkillTag.name)
    ).all()
    return [
        SkillMasteryOut(
            skill_tag_id=r.id,
            skill_tag_name=r.name,
            mastery=r.mastery,
            sample_size=r.sample_size,
            insufficient_data=r.sample_size < SNAPSHOT_MIN_CONFIDENT_SAMPLE,
        )
        for r in rows
    ]


def _topic_trends(
    published: list[Topic],
    topic_snapshots: dict[int, PerformanceSnapshot],
) -> list[TopicTrendOut]:
    return [
        TopicTrendOut(
            topic_slug=t.slug,
            topic_title=t.title,
            trend=topic_snapshots[t.id].trend,
        )
        for t in published
        if t.id in topic_snapshots
    ]


def _recommendations(
    db: Session,
    published: list[Topic],
    topic_snapshots: dict[int, PerformanceSnapshot],
) -> list[RecommendationOut]:
    by_id = {t.id: t for t in published}
    nodes = {
        t.id: TopicNode(
            topic_id=t.id,
            order=i,
            prerequisite_ids=tuple(
                p.id for p in t.prerequisites if p.id in by_id
            ),
        )
        for i, t in enumerate(published)
    }
    masteries = {
        tid: snap.mastery for tid, snap in topic_snapshots.items()
    }

    settings = AnalyticsSettings(db)
    picks = recommend(
        masteries=masteries,
        topics=nodes,
        threshold=settings.mastery_threshold,
        limit=settings.recommendation_count,
    )

    out: list[RecommendationOut] = []
    for pick in picks:
        topic = by_id[pick.topic_id]
        for_topic = (
            by_id[pick.for_topic_id]
            if pick.for_topic_id is not None
            else None
        )
        out.append(
            RecommendationOut(
                topic_slug=topic.slug,
                topic_title=topic.title,
                reason=pick.reason,
                mastery=pick.mastery,
                for_topic_slug=for_topic.slug if for_topic else None,
                for_topic_title=for_topic.title if for_topic else None,
            )
        )
    return out


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
