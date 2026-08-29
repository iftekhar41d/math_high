"""The snapshot-backed dashboard views (ticket 02): skill-tag heatmap, per-Topic
trend, and "study this next" recommendations.

Each test seeds real `QuestionAttempt` rows, runs the real recompute
(`app.analytics.recompute.recompute`) against the shared test database, then
asserts the `GET /dashboard` payload. The pure selection maths is unit-tested
in `test_recommendations.py`.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.analytics.recompute import recompute
from app.models import (
    CONTENT_DRAFT,
    CONTENT_PUBLISHED,
    LectureContent,
    Question,
    QuestionAttempt,
    SkillTag,
    Subject,
    Topic,
    Unit,
    User,
    YearLevel,
)
from sqlalchemy import func

from app.settings_store import write_setting
from tests.fakes import DEFAULT_START, FakeClock
from tests.test_auth import register_and_verify
from tests.test_auth import login as _login

NOW = DEFAULT_START


@pytest.fixture
def student(client, fake_email, db_session):
    """A verified student; returns `(headers, user_id)`."""
    creds = register_and_verify(client, fake_email)
    token = _login(client, creds).json()["access_token"]
    user_id = (
        db_session.query(User)
        .filter(func.lower(User.email) == creds["email"].lower())
        .one()
        .id
    )
    return {"Authorization": f"Bearer {token}"}, user_id


@pytest.fixture
def syllabus(db_session):
    """Year 7 -> Mathematics with two Units:

    Number:  integers (o1), decimals (o2)
    Algebra: variables (o1), expressions (o2, prereq variables),
             algebra (o3, prereq expressions), advanced (o4, DRAFT)

    Two SkillTags (`adding`, `ordering`) hang off the integers questions.
    Every published Topic gets four numeric questions so tests can vary the
    sample size; `advanced` gets one.
    """
    y7 = YearLevel(name="Year 7", syllabus_region="AU-NSW")
    db_session.add(y7)
    db_session.flush()
    maths = Subject(year_level_id=y7.id, title="Mathematics", order=1)
    db_session.add(maths)
    db_session.flush()
    number = Unit(subject_id=maths.id, title="Number", order=1)
    algebra_u = Unit(subject_id=maths.id, title="Algebra", order=2)
    db_session.add_all([number, algebra_u])
    db_session.flush()

    def topic(unit, title, slug, order, status=CONTENT_PUBLISHED):
        t = Topic(unit_id=unit.id, title=title, slug=slug, order=order)
        db_session.add(t)
        db_session.flush()
        db_session.add(
            LectureContent(
                topic_id=t.id, body=f"# {title}", status=status, version=1
            )
        )
        return t

    integers = topic(number, "Integers", "integers", 1)
    decimals = topic(number, "Decimals", "decimals", 2)
    variables = topic(algebra_u, "Variables", "variables", 1)
    expressions = topic(algebra_u, "Expressions", "expressions", 2)
    algebra = topic(algebra_u, "Algebra", "algebra", 3)
    advanced = topic(algebra_u, "Advanced", "advanced", 4, CONTENT_DRAFT)

    expressions.prerequisites = [variables]
    algebra.prerequisites = [expressions]

    adding = SkillTag(name="adding")
    ordering = SkillTag(name="ordering")
    db_session.add_all([adding, ordering])
    db_session.flush()

    topics = {
        "integers": integers,
        "decimals": decimals,
        "variables": variables,
        "expressions": expressions,
        "algebra": algebra,
        "advanced": advanced,
    }
    questions: dict[str, list[Question]] = {}
    for key, t in topics.items():
        n = 1 if key == "advanced" else 4
        qs = []
        for i in range(n):
            q = Question(
                topic_id=t.id,
                type="numeric",
                difficulty="easy",
                body=f"{key} q{i}",
                answer_schema={"value": 1, "tolerance": 0.1},
                worked_solution="s",
            )
            db_session.add(q)
            db_session.flush()
            qs.append(q)
        questions[key] = qs

    # adding: tag q0..q2 of integers; ordering: tag q3 of integers.
    for q in questions["integers"][:3]:
        q.skill_tags = [adding]
    questions["integers"][3].skill_tags = [ordering]

    db_session.commit()
    return {"topics": topics, "questions": questions,
            "tags": {"adding": adding, "ordering": ordering}}


def _attempt(db_session, user_id, question, *, correct, at=NOW, attempt_no=1):
    db_session.add(
        QuestionAttempt(
            user_id=user_id,
            question_id=question.id,
            submitted_answer=1,
            is_correct=correct,
            attempt_no=attempt_no,
            created_at=at,
        )
    )


def _run_recompute(db_session):
    db_session.commit()
    recompute(db_session, FakeClock(NOW), full=True)


def _dashboard(client, headers):
    resp = client.get("/dashboard", headers=headers)
    assert resp.status_code == 200
    return resp.json()


# -- skill-tag heatmap ---------------------------------------------------


def test_skill_mastery_reports_cached_value_and_sample_size(
    client, db_session, syllabus, student
):
    headers, uid = student
    q = syllabus["questions"]
    # adding: 3 first attempts, 2 correct -> 2/3. ordering: 1 attempt, wrong.
    _attempt(db_session, uid, q["integers"][0], correct=True)
    _attempt(db_session, uid, q["integers"][1], correct=True)
    _attempt(db_session, uid, q["integers"][2], correct=False)
    _attempt(db_session, uid, q["integers"][3], correct=False)
    _run_recompute(db_session)

    skills = {s["skill_tag_name"]: s for s in _dashboard(client, headers)[
        "skill_mastery"
    ]}
    assert set(skills) == {"adding", "ordering"}
    assert skills["adding"]["mastery"] == pytest.approx(2 / 3)
    assert skills["adding"]["sample_size"] == 3
    assert skills["adding"]["insufficient_data"] is False
    assert skills["ordering"]["mastery"] == pytest.approx(0.0)
    assert skills["ordering"]["sample_size"] == 1
    assert skills["ordering"]["insufficient_data"] is True


def test_skill_mastery_is_empty_before_the_recompute_runs(
    client, db_session, syllabus, student
):
    headers, uid = student
    _attempt(db_session, uid, syllabus["questions"]["integers"][0], correct=True)
    db_session.commit()  # no recompute

    assert _dashboard(client, headers)["skill_mastery"] == []


# -- per-Topic trend ---------------------------------------------------


def test_topic_trends_report_the_cached_direction_in_syllabus_order(
    client, db_session, syllabus, student
):
    headers, uid = student
    q = syllabus["questions"]
    # decimals: prior window wrong, recent window right -> up.
    _attempt(db_session, uid, q["decimals"][0], correct=False,
             at=NOW - timedelta(days=45))
    _attempt(db_session, uid, q["decimals"][1], correct=False,
             at=NOW - timedelta(days=45))
    _attempt(db_session, uid, q["decimals"][2], correct=True,
             at=NOW - timedelta(days=5))
    _attempt(db_session, uid, q["decimals"][3], correct=True,
             at=NOW - timedelta(days=5))
    # integers: one recent attempt only -> flat (a window is empty).
    _attempt(db_session, uid, q["integers"][0], correct=True)
    _run_recompute(db_session)

    trends = _dashboard(client, headers)["topic_trends"]
    # syllabus order: integers (Number o1) before decimals (Number o2).
    assert [t["topic_slug"] for t in trends] == ["integers", "decimals"]
    by_slug = {t["topic_slug"]: t for t in trends}
    assert by_slug["decimals"]["trend"] == "up"
    assert by_slug["integers"]["trend"] == "flat"
    assert by_slug["decimals"]["topic_title"] == "Decimals"


def test_draft_topics_never_appear_in_trends(
    client, db_session, syllabus, student
):
    headers, uid = student
    _attempt(db_session, uid, syllabus["questions"]["advanced"][0],
             correct=False)
    _run_recompute(db_session)

    slugs = [t["topic_slug"] for t in _dashboard(client, headers)[
        "topic_trends"
    ]]
    assert "advanced" not in slugs


# -- per-Topic percentage is still live ------------------------------


def test_topic_percentage_is_still_computed_live_from_attempts(
    client, db_session, syllabus, student
):
    headers, uid = student
    q = syllabus["questions"]
    _attempt(db_session, uid, q["integers"][0], correct=True)
    _attempt(db_session, uid, q["integers"][1], correct=False)
    _run_recompute(db_session)

    perf = {p["topic_slug"]: p for p in _dashboard(client, headers)[
        "topic_performance"
    ]}
    assert perf["integers"]["attempts"] == 2
    assert perf["integers"]["correct"] == 1
    assert perf["integers"]["percent_correct"] == 50.0


# -- recommendations -------------------------------------------------


def _weak(db_session, uid, questions, n_correct):
    """First `n_correct` of the four questions correct, the rest wrong — an
    all-at-NOW mastery of `n_correct / 4`."""
    for i, q in enumerate(questions):
        _attempt(db_session, uid, q, correct=i < n_correct)


def test_recommendations_pick_weak_ready_topics_lowest_first(
    client, db_session, syllabus, student
):
    headers, uid = student
    q = syllabus["questions"]
    _weak(db_session, uid, q["integers"], 4)      # 1.0 — solid, not picked
    _weak(db_session, uid, q["variables"], 1)     # 0.25 — weak, ready
    _weak(db_session, uid, q["decimals"], 2)      # 0.5  — weak, ready
    _run_recompute(db_session)

    recs = _dashboard(client, headers)["recommendations"]
    assert [(r["topic_slug"], r["reason"]) for r in recs] == [
        ("variables", "practice"),
        ("decimals", "practice"),
    ]
    assert recs[0]["mastery"] == pytest.approx(0.25)
    assert "integers" not in [r["topic_slug"] for r in recs]


def test_recommendation_count_setting_caps_the_list(
    client, db_session, syllabus, student
):
    headers, uid = student
    q = syllabus["questions"]
    _weak(db_session, uid, q["variables"], 1)
    _weak(db_session, uid, q["decimals"], 2)
    write_setting(db_session, "analytics.recommendation_count", "1")
    _run_recompute(db_session)

    recs = _dashboard(client, headers)["recommendations"]
    assert [r["topic_slug"] for r in recs] == ["variables"]


def test_recommendation_threshold_setting_widens_the_net(
    client, db_session, syllabus, student
):
    headers, uid = student
    _weak(db_session, uid, syllabus["questions"]["decimals"], 3)  # 0.75
    write_setting(db_session, "analytics.mastery_threshold", "0.8")
    _run_recompute(db_session)

    recs = _dashboard(client, headers)["recommendations"]
    assert [r["topic_slug"] for r in recs] == ["decimals"]


def test_weaker_prerequisite_is_recommended_instead_of_the_topic(
    client, db_session, syllabus, student
):
    headers, uid = student
    q = syllabus["questions"]
    # variables 0.5 (weak, ready), expressions 0.0 (weak; prereq variables is
    # weak but NOT lower -> expressions is never a direct pick), algebra 0.5
    # (weak; prereq expressions scores lower -> "revise expressions").
    _weak(db_session, uid, q["variables"], 2)
    _weak(db_session, uid, q["expressions"], 0)
    _weak(db_session, uid, q["algebra"], 2)
    _run_recompute(db_session)

    recs = _dashboard(client, headers)["recommendations"]
    by_slug = {r["topic_slug"]: r for r in recs}

    # algebra itself is not offered — its weaker prerequisite stands in.
    assert "algebra" not in by_slug
    assert by_slug["expressions"]["reason"] == "revise_prerequisite"
    assert by_slug["expressions"]["for_topic_slug"] == "algebra"
    assert by_slug["expressions"]["for_topic_title"] == "Algebra"
    # variables is still its own plain practice pick, and sorts after the
    # lower-mastery substitution.
    assert by_slug["variables"]["reason"] == "practice"
    assert [r["topic_slug"] for r in recs] == ["expressions", "variables"]


def test_recommendations_ignore_draft_topics(
    client, db_session, syllabus, student
):
    headers, uid = student
    _weak(db_session, uid, syllabus["questions"]["advanced"][:1], 0)
    _run_recompute(db_session)

    recs = _dashboard(client, headers)["recommendations"]
    assert recs == []
