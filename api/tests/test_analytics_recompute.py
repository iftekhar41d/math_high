"""`app.analytics.recompute` — snapshot rows, mastery / trend / sample-size
maths, the sub-3 sample case, watermark no-op behaviour, and the CLI wrapper.

These drive the reusable core (`recompute`) directly with a hand-built attempt
history and the `FakeClock`, plus one test that runs the module CLI against the
ephemeral test database.
"""

from __future__ import annotations

import importlib
from datetime import timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.analytics.mastery import FirstAttempt, time_weighted_mastery, trend
from app.analytics.recompute import recompute
from app.analytics.settings import (
    DEFAULT_MASTERY_HALF_LIFE_DAYS,
    AnalyticsSettings,
)
from app.models import (
    SNAPSHOT_DIMENSION_SKILL_TAG,
    SNAPSHOT_DIMENSION_TOPIC,
    TREND_DOWN,
    TREND_FLAT,
    TREND_UP,
    PerformanceSnapshot,
    Question,
    QuestionAttempt,
    SkillTag,
    Subject,
    Topic,
    TopicView,
    Unit,
    User,
    YearLevel,
)
from tests.fakes import DEFAULT_START, FakeClock

# -- pure mastery maths ---------------------------------------------------


def test_time_weighted_mastery_halves_at_the_half_life():
    now = DEFAULT_START
    hl = DEFAULT_MASTERY_HALF_LIFE_DAYS
    attempts = [
        FirstAttempt(correct=True, at=now),  # weight 1.0
        FirstAttempt(correct=False, at=now - timedelta(days=hl)),  # weight 0.5
    ]
    assert time_weighted_mastery(
        attempts, now=now, half_life_days=hl
    ) == pytest.approx(1.0 / 1.5)


def test_recent_correct_beats_old_correct_and_recent_wrong():
    now = DEFAULT_START
    hl = DEFAULT_MASTERY_HALF_LIFE_DAYS
    fresh_win = time_weighted_mastery(
        [
            FirstAttempt(correct=True, at=now),
            FirstAttempt(correct=False, at=now - timedelta(days=90)),
        ],
        now=now,
        half_life_days=hl,
    )
    stale_win = time_weighted_mastery(
        [
            FirstAttempt(correct=False, at=now),
            FirstAttempt(correct=True, at=now - timedelta(days=90)),
        ],
        now=now,
        half_life_days=hl,
    )
    assert fresh_win > 0.9
    assert stale_win < 0.1


def test_trend_is_flat_when_either_window_is_empty():
    now = DEFAULT_START
    only_recent = [FirstAttempt(correct=True, at=now - timedelta(days=3))]
    assert (
        trend(only_recent, now=now, half_life_days=14.0) == "flat"
    )


# -- fixture helpers --------------------------------------------------------


@pytest.fixture
def tree(db_session):
    """Year 7 -> Mathematics -> Number -> "Integers", plus two SkillTags. Tests
    add their own Questions and attempts on top."""
    y7 = YearLevel(name="Year 7", syllabus_region="AU-NSW")
    db_session.add(y7)
    db_session.flush()
    maths = Subject(year_level_id=y7.id, title="Mathematics", order=1)
    db_session.add(maths)
    db_session.flush()
    number = Unit(subject_id=maths.id, title="Number", order=1)
    db_session.add(number)
    db_session.flush()
    integers = Topic(
        unit_id=number.id, title="Integers", slug="integers", order=1
    )
    db_session.add(integers)
    db_session.flush()
    adding = SkillTag(name="adding")
    ordering = SkillTag(name="ordering")
    db_session.add_all([adding, ordering])
    db_session.flush()
    return {
        "topic": integers,
        "adding": adding,
        "ordering": ordering,
        "unit": number,
    }


def _question(db, topic, *tags):
    q = Question(
        topic_id=topic.id,
        type="numeric",
        difficulty="easy",
        body="q",
        answer_schema={"value": 1, "tolerance": 0.1},
        worked_solution="s",
    )
    q.skill_tags = list(tags)
    db.add(q)
    db.flush()
    return q


def _student(db, email="ada@example.com"):
    u = User(email=email, name="Ada", year_level=7)
    db.add(u)
    db.flush()
    return u


def _attempt(
    db,
    user,
    question,
    *,
    correct,
    at,
    attempt_no=1,
    solution_viewed=False,
):
    row = QuestionAttempt(
        user_id=user.id,
        question_id=question.id,
        submitted_answer=1 if attempt_no else None,
        is_correct=correct,
        attempt_no=attempt_no,
        solution_viewed=solution_viewed,
        created_at=at,
    )
    db.add(row)
    db.flush()
    return row


def _snapshots(db, user_id):
    rows = db.query(PerformanceSnapshot).filter_by(user_id=user_id).all()
    return {(r.dimension, r.dimension_id): r for r in rows}


# -- snapshot rows: one per Topic and per SkillTag ------------------------


def test_recompute_writes_one_row_per_topic_and_per_skill_tag(
    db_session, tree
):
    now = DEFAULT_START
    clock = FakeClock(now)
    ada = _student(db_session)
    q1 = _question(db_session, tree["topic"], tree["adding"])
    q2 = _question(db_session, tree["topic"], tree["adding"], tree["ordering"])
    # q1: correct now (weight 1). q2: incorrect 14 days ago (weight 0.5).
    _attempt(db_session, ada, q1, correct=True, at=now)
    _attempt(
        db_session, ada, q2, correct=False, at=now - timedelta(days=14)
    )
    db_session.commit()

    summary = recompute(db_session, clock, full=True)
    assert summary.ran is True
    assert summary.students == 1

    snaps = _snapshots(db_session, ada.id)
    topic_key = (SNAPSHOT_DIMENSION_TOPIC, tree["topic"].id)
    adding_key = (SNAPSHOT_DIMENSION_SKILL_TAG, tree["adding"].id)
    ordering_key = (SNAPSHOT_DIMENSION_SKILL_TAG, tree["ordering"].id)
    assert set(snaps) == {topic_key, adding_key, ordering_key}

    # Topic + "adding" both see {correct@w1, incorrect@w0.5} -> 1 / 1.5.
    assert snaps[topic_key].mastery == pytest.approx(1.0 / 1.5)
    assert snaps[topic_key].sample_size == 2
    assert snaps[adding_key].mastery == pytest.approx(1.0 / 1.5)
    assert snaps[adding_key].sample_size == 2
    # "ordering" only tags q2 -> a single incorrect first attempt.
    assert snaps[ordering_key].mastery == pytest.approx(0.0)
    assert snaps[ordering_key].sample_size == 1
    assert snaps[topic_key].computed_at == now


def test_sub_three_sample_size_still_writes_the_row(db_session, tree):
    now = DEFAULT_START
    ada = _student(db_session)
    q1 = _question(db_session, tree["topic"], tree["adding"])
    _attempt(db_session, ada, q1, correct=True, at=now)
    db_session.commit()

    recompute(db_session, FakeClock(now), full=True)

    snaps = _snapshots(db_session, ada.id)
    row = snaps[(SNAPSHOT_DIMENSION_TOPIC, tree["topic"].id)]
    assert row.sample_size == 1
    assert row.mastery == pytest.approx(1.0)


# -- mastery uses the FIRST graded attempt only --------------------------


def test_only_the_first_graded_attempt_counts(db_session, tree):
    now = DEFAULT_START
    ada = _student(db_session)
    q1 = _question(db_session, tree["topic"], tree["adding"])
    # First attempt wrong, retried right — mastery must see the wrong one.
    _attempt(db_session, ada, q1, correct=False, at=now, attempt_no=1)
    _attempt(db_session, ada, q1, correct=True, at=now, attempt_no=2)
    db_session.commit()

    recompute(db_session, FakeClock(now), full=True)

    row = _snapshots(db_session, ada.id)[
        (SNAPSHOT_DIMENSION_TOPIC, tree["topic"].id)
    ]
    assert row.mastery == pytest.approx(0.0)
    assert row.sample_size == 1


# -- solution viewed before the first submission counts incorrect --------


def test_solution_viewed_before_first_submission_is_incorrect(
    db_session, tree
):
    now = DEFAULT_START
    ada = _student(db_session)
    q_marker = _question(db_session, tree["topic"], tree["adding"])
    q_after = _question(db_session, tree["topic"], tree["adding"])
    q_then_right = _question(db_session, tree["topic"], tree["adding"])

    # Marker-only row: viewed the solution, never submitted.
    _attempt(
        db_session,
        ada,
        q_marker,
        correct=None,
        at=now,
        attempt_no=0,
        solution_viewed=True,
    )
    # Submitted right, then viewed the solution — the reveal was *after*.
    _attempt(
        db_session,
        ada,
        q_after,
        correct=True,
        at=now,
        attempt_no=1,
        solution_viewed=True,
    )
    # Viewed first (marker), later submitted right — still counts incorrect.
    _attempt(
        db_session,
        ada,
        q_then_right,
        correct=None,
        at=now,
        attempt_no=0,
        solution_viewed=True,
    )
    _attempt(
        db_session, ada, q_then_right, correct=True, at=now, attempt_no=1
    )
    db_session.commit()

    recompute(db_session, FakeClock(now), full=True)

    row = _snapshots(db_session, ada.id)[
        (SNAPSHOT_DIMENSION_TOPIC, tree["topic"].id)
    ]
    # incorrect, correct, incorrect -> 1 of 3, all at weight 1.
    assert row.sample_size == 3
    assert row.mastery == pytest.approx(1.0 / 3.0)


def test_mentisq_used_does_not_move_mastery(db_session, tree):
    now = DEFAULT_START
    ada = _student(db_session)
    q1 = _question(db_session, tree["topic"], tree["adding"])
    row = _attempt(db_session, ada, q1, correct=True, at=now)
    row.mentisq_used = True
    db_session.commit()

    recompute(db_session, FakeClock(now), full=True)

    snap = _snapshots(db_session, ada.id)[
        (SNAPSHOT_DIMENSION_TOPIC, tree["topic"].id)
    ]
    assert snap.mastery == pytest.approx(1.0)


# -- trend buckets --------------------------------------------------------


def _trend_fixture(db_session, tree, *, prior_correct, recent_correct):
    """Two first attempts in the prior 30-day window and two in the recent one,
    with the given correctness, all on distinct Questions in the Topic."""
    now = DEFAULT_START
    ada = _student(db_session)
    prior_at = now - timedelta(days=45)
    recent_at = now - timedelta(days=5)
    for correct in prior_correct:
        q = _question(db_session, tree["topic"], tree["adding"])
        _attempt(db_session, ada, q, correct=correct, at=prior_at)
    for correct in recent_correct:
        q = _question(db_session, tree["topic"], tree["adding"])
        _attempt(db_session, ada, q, correct=correct, at=recent_at)
    db_session.commit()
    recompute(db_session, FakeClock(now), full=True)
    return _snapshots(db_session, ada.id)[
        (SNAPSHOT_DIMENSION_TOPIC, tree["topic"].id)
    ]


def test_trend_up_when_recent_window_beats_the_prior(db_session, tree):
    row = _trend_fixture(
        db_session, tree, prior_correct=[False, False], recent_correct=[True, True]
    )
    assert row.trend == TREND_UP


def test_trend_down_when_recent_window_trails_the_prior(db_session, tree):
    row = _trend_fixture(
        db_session, tree, prior_correct=[True, True], recent_correct=[False, False]
    )
    assert row.trend == TREND_DOWN


def test_trend_flat_inside_the_dead_zone(db_session, tree):
    row = _trend_fixture(
        db_session, tree, prior_correct=[True, False], recent_correct=[True, False]
    )
    assert row.trend == TREND_FLAT


def test_trend_flat_when_a_window_has_no_samples(db_session, tree):
    now = DEFAULT_START
    ada = _student(db_session)
    q = _question(db_session, tree["topic"], tree["adding"])
    _attempt(db_session, ada, q, correct=True, at=now)  # recent only
    db_session.commit()
    recompute(db_session, FakeClock(now), full=True)
    row = _snapshots(db_session, ada.id)[
        (SNAPSHOT_DIMENSION_TOPIC, tree["topic"].id)
    ]
    assert row.trend == TREND_FLAT


# -- incremental watermark ----------------------------------------------


def test_second_run_with_no_new_activity_writes_nothing(db_session, tree):
    now = DEFAULT_START
    ada = _student(db_session)
    q = _question(db_session, tree["topic"], tree["adding"])
    _attempt(db_session, ada, q, correct=True, at=now)
    db_session.commit()

    clock = FakeClock(now)
    first = recompute(db_session, clock, full=True)
    assert first.snapshots_written == 2  # topic + one skill tag
    stamped = _snapshots(db_session, ada.id)[
        (SNAPSHOT_DIMENSION_TOPIC, tree["topic"].id)
    ].computed_at

    clock.advance(timedelta(days=1))
    second = recompute(db_session, clock, full=False)
    assert second.ran is False
    assert second.students == 0
    # The existing row was not rewritten.
    assert _snapshots(db_session, ada.id)[
        (SNAPSHOT_DIMENSION_TOPIC, tree["topic"].id)
    ].computed_at == stamped


def test_incremental_run_only_revisits_students_with_new_activity(
    db_session, tree
):
    t0 = DEFAULT_START
    clock = FakeClock(t0)
    ada = _student(db_session, "ada@example.com")
    bob = _student(db_session, "bob@example.com")
    q = _question(db_session, tree["topic"], tree["adding"])
    _attempt(db_session, ada, q, correct=True, at=t0)
    _attempt(db_session, bob, q, correct=True, at=t0)
    db_session.commit()

    recompute(db_session, clock, full=True)
    ada_stamp = _snapshots(db_session, ada.id)[
        (SNAPSHOT_DIMENSION_TOPIC, tree["topic"].id)
    ].computed_at

    # Only Bob does something new.
    clock.advance(timedelta(days=2))
    _attempt(db_session, bob, q, correct=False, at=clock.now(), attempt_no=2)
    db_session.commit()

    clock.advance(timedelta(hours=1))
    summary = recompute(db_session, clock, full=False)
    assert summary.students == 1

    assert _snapshots(db_session, ada.id)[
        (SNAPSHOT_DIMENSION_TOPIC, tree["topic"].id)
    ].computed_at == ada_stamp
    assert _snapshots(db_session, bob.id)[
        (SNAPSHOT_DIMENSION_TOPIC, tree["topic"].id)
    ].computed_at == clock.now()


def test_topic_view_alone_makes_a_student_active(db_session, tree):
    t0 = DEFAULT_START
    clock = FakeClock(t0)
    ada = _student(db_session)
    q = _question(db_session, tree["topic"], tree["adding"])
    _attempt(db_session, ada, q, correct=True, at=t0)
    db_session.commit()
    recompute(db_session, clock, full=True)

    clock.advance(timedelta(days=3))
    db_session.add(
        TopicView(
            user_id=ada.id, topic_id=tree["topic"].id, created_at=clock.now()
        )
    )
    db_session.commit()

    clock.advance(timedelta(hours=1))
    summary = recompute(db_session, clock, full=False)
    assert summary.students == 1
    assert _snapshots(db_session, ada.id)[
        (SNAPSHOT_DIMENSION_TOPIC, tree["topic"].id)
    ].computed_at == clock.now()


def test_watermark_is_persisted_between_runs(db_session, tree):
    now = DEFAULT_START
    ada = _student(db_session)
    q = _question(db_session, tree["topic"], tree["adding"])
    _attempt(db_session, ada, q, correct=True, at=now)
    db_session.commit()

    recompute(db_session, FakeClock(now), full=True)
    assert AnalyticsSettings(db_session).watermark == now


# -- the CLI wrapper ----------------------------------------------------


def test_cli_recomputes_against_the_configured_database(
    db_engine, db_session, tree, monkeypatch
):
    now = DEFAULT_START
    ada = _student(db_session)
    q = _question(db_session, tree["topic"], tree["adding"])
    _attempt(db_session, ada, q, correct=True, at=now)
    db_session.commit()

    recompute_mod = importlib.import_module("app.analytics.recompute")

    Session = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(recompute_mod, "SessionLocal", Session)
    monkeypatch.setattr(recompute_mod, "Clock", lambda: FakeClock(now))

    assert recompute_mod.main(["--full"]) == 0

    snaps = _snapshots(db_session, ada.id)
    assert (SNAPSHOT_DIMENSION_TOPIC, tree["topic"].id) in snaps
