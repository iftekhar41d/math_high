"""`python -m app.analytics.recompute [--full]` — rebuild `PerformanceSnapshot`.

Shaped like `python -m app.ingest`: a thin CLI (`main`) over a reusable core
(`recompute`), the same `SessionLocal` / `Clock` indirection, run from inside
`api/`.

`recompute(db, clock, *, full=False)`:

- picks the students to revisit — everyone with a graded attempt on a `--full`
  run, otherwise only those with a `QuestionAttempt` or `TopicView` strictly
  after the stored watermark;
- for each, reduces their `QuestionAttempt` rows to one `FirstAttempt` per
  Question (the first graded submission; but a solution viewed *before* any
  submission forces that Question to count incorrect), fans each out to its
  Topic and every SkillTag it carries, and upserts one snapshot row per
  (dimension, dimension_id) with the recency-weighted mastery, the bucketed
  trend, and the contributing sample size;
- advances the watermark to the run's start instant and commits.

An incremental run that finds no active students writes nothing at all — the
watermark is left untouched.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.analytics.mastery import FirstAttempt, time_weighted_mastery, trend
from app.analytics.settings import AnalyticsSettings
from app.clock import Clock
from app.database import SessionLocal
from app.models import (
    SNAPSHOT_DIMENSION_SKILL_TAG,
    SNAPSHOT_DIMENSION_TOPIC,
    PerformanceSnapshot,
    Question,
    QuestionAttempt,
    TopicView,
)


@dataclass
class RecomputeSummary:
    students: int = 0
    snapshots_written: int = 0
    # True on a `--full` run or an incremental run that found active students;
    # False when an incremental run short-circuited with nothing to do.
    ran: bool = True
    dimensions: dict[str, int] = field(
        default_factory=lambda: {
            SNAPSHOT_DIMENSION_TOPIC: 0,
            SNAPSHOT_DIMENSION_SKILL_TAG: 0,
        }
    )


def recompute(
    db: Session,
    clock: Clock,
    *,
    full: bool = False,
) -> RecomputeSummary:
    now = clock.now()
    settings = AnalyticsSettings(db)
    watermark = None if full else settings.watermark

    user_ids = _active_user_ids(db, watermark, full=full)
    if not user_ids and not full:
        # Nothing happened since the last run — don't even move the watermark.
        return RecomputeSummary(ran=False)

    summary = RecomputeSummary()
    half_life = settings.mastery_half_life_days
    for user_id in sorted(user_ids):
        summary.students += 1
        _recompute_user(db, user_id, now=now, half_life=half_life, summary=summary)

    settings.set_watermark(now)
    db.commit()
    return summary


def _active_user_ids(
    db: Session, watermark: datetime | None, *, full: bool
) -> set[int]:
    if full or watermark is None:
        return set(
            db.scalars(select(QuestionAttempt.user_id).distinct()).all()
        )
    attempts = db.scalars(
        select(QuestionAttempt.user_id)
        .where(QuestionAttempt.created_at > watermark)
        .distinct()
    ).all()
    views = db.scalars(
        select(TopicView.user_id)
        .where(TopicView.created_at > watermark)
        .distinct()
    ).all()
    return set(attempts) | set(views)


def _recompute_user(
    db: Session,
    user_id: int,
    *,
    now: datetime,
    half_life: float,
    summary: RecomputeSummary,
) -> None:
    attempts = db.scalars(
        select(QuestionAttempt).where(QuestionAttempt.user_id == user_id)
    ).all()
    by_question: dict[int, list[QuestionAttempt]] = defaultdict(list)
    for row in attempts:
        by_question[row.question_id].append(row)

    questions = db.scalars(
        select(Question)
        .where(Question.id.in_(list(by_question.keys())))
        .options(selectinload(Question.skill_tags))
    ).all()
    question_by_id = {q.id: q for q in questions}

    by_topic: dict[int, list[FirstAttempt]] = defaultdict(list)
    by_skill: dict[int, list[FirstAttempt]] = defaultdict(list)
    for question_id, rows in by_question.items():
        question = question_by_id.get(question_id)
        if question is None:  # attempt against a since-deleted Question
            continue
        first = _first_attempt(rows)
        if first is None:
            continue
        by_topic[question.topic_id].append(first)
        for tag in question.skill_tags:
            by_skill[tag.id].append(first)

    for dimension, buckets in (
        (SNAPSHOT_DIMENSION_TOPIC, by_topic),
        (SNAPSHOT_DIMENSION_SKILL_TAG, by_skill),
    ):
        for dimension_id, first_attempts in buckets.items():
            _upsert_snapshot(
                db,
                user_id=user_id,
                dimension=dimension,
                dimension_id=dimension_id,
                mastery=time_weighted_mastery(
                    first_attempts, now=now, half_life_days=half_life
                ),
                trend_direction=trend(
                    first_attempts, now=now, half_life_days=half_life
                ),
                sample_size=len(first_attempts),
                computed_at=now,
            )
            summary.snapshots_written += 1
            summary.dimensions[dimension] += 1


def _first_attempt(rows: list[QuestionAttempt]) -> FirstAttempt | None:
    """Reduce every attempt row for one (user, Question) to its first-attempt
    outcome, or `None` if there is nothing gradable.

    A marker row (`attempt_no == 0`, `solution_viewed`) means the student saw
    the worked solution before ever submitting — that Question counts incorrect
    regardless of any later submission. Otherwise the outcome is the first
    graded submission's correctness. The timestamp anchors on that first graded
    submission; only a solution viewed and never followed by a submission falls
    back to the marker row's time.
    """
    graded = [r for r in rows if (r.attempt_no or 0) > 0]
    solution_first = any(
        (r.attempt_no or 0) == 0 and r.solution_viewed for r in rows
    )
    if not graded and not solution_first:
        return None

    if graded:
        first_graded = min(graded, key=lambda r: (r.attempt_no, r.created_at))
        return FirstAttempt(
            correct=False if solution_first else bool(first_graded.is_correct),
            at=first_graded.created_at,
        )
    # Solution viewed, never submitted — engaged at the marker row.
    return FirstAttempt(correct=False, at=min(r.created_at for r in rows))


def _upsert_snapshot(
    db: Session,
    *,
    user_id: int,
    dimension: str,
    dimension_id: int,
    mastery: float,
    trend_direction: str,
    sample_size: int,
    computed_at: datetime,
) -> None:
    row = db.scalar(
        select(PerformanceSnapshot).where(
            PerformanceSnapshot.user_id == user_id,
            PerformanceSnapshot.dimension == dimension,
            PerformanceSnapshot.dimension_id == dimension_id,
        )
    )
    if row is None:
        db.add(
            PerformanceSnapshot(
                user_id=user_id,
                dimension=dimension,
                dimension_id=dimension_id,
                mastery=mastery,
                trend=trend_direction,
                sample_size=sample_size,
                computed_at=computed_at,
            )
        )
    else:
        row.mastery = mastery
        row.trend = trend_direction
        row.sample_size = sample_size
        row.computed_at = computed_at


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.analytics.recompute",
        description="Rebuild cached PerformanceSnapshot rows from attempt history.",
    )
    parser.add_argument(
        "--full",
        dest="full",
        action="store_true",
        help="recompute every student, ignoring the incremental watermark",
    )
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        summary = recompute(db, Clock(), full=args.full)
    finally:
        db.close()

    if not summary.ran:
        print("recompute: no activity since the last run — nothing to do")
        return 0
    print(
        f"recompute: {summary.students} students, "
        f"{summary.snapshots_written} snapshots "
        f"({summary.dimensions[SNAPSHOT_DIMENSION_TOPIC]} topic, "
        f"{summary.dimensions[SNAPSHOT_DIMENSION_SKILL_TAG]} skill_tag)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
