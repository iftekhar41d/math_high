"""Mixed practice mode — the pure selection maths and the HTTP flow.

`app.practice.mixed.select_mixed_questions` is deterministic given its `rng`, so
the weighting is asserted directly at that seam; the HTTP tests then cover the
plumbing — the frozen set, `question_count`, immediate feedback, and scope
resolution.
"""

from __future__ import annotations

import random

import pytest

from app.models import (
    CONTENT_DRAFT,
    CONTENT_PUBLISHED,
    PRACTICE_MODE_MIXED,
    PRACTICE_SCOPE_UNIT,
    PRACTICE_SCOPE_YEAR_LEVEL,
    SNAPSHOT_DIMENSION_SKILL_TAG,
    SNAPSHOT_DIMENSION_TOPIC,
    LectureContent,
    PerformanceSnapshot,
    PracticeSession,
    PracticeSessionQuestion,
    Question,
    QuestionAttempt,
    SkillTag,
    Subject,
    Topic,
    Unit,
    User,
    YearLevel,
)
from app.practice.mixed import (
    DEFAULT_MIXED_QUESTION_COUNT,
    Candidate,
    select_mixed_questions,
)
from tests.test_content import _content_admin, _student


# -- pure selection --------------------------------------------------------


def test_cold_start_is_even_skilltag_coverage_difficulty_ascending():
    cands = [
        Candidate(1, "hard", (1,)),
        Candidate(2, "easy", (1,)),
        Candidate(3, "medium", (2,)),
        Candidate(4, "easy", (2,)),
        Candidate(5, "hard", (3,)),
    ]
    picked = select_mixed_questions(
        cands, skill_mastery={}, question_count=3, rng=random.Random(0)
    )
    # Round-robin tags 1, 2, 3 takes the easiest unused of each: q2, q4, q5.
    # Returned difficulty-ascending (then id): easy q2, easy q4, hard q5.
    assert picked == [2, 4, 5]


def test_cold_start_returns_all_when_fewer_candidates_than_asked():
    cands = [
        Candidate(1, "hard", (1,)),
        Candidate(2, "easy", (1,)),
        Candidate(3, "medium", (2,)),
    ]
    picked = select_mixed_questions(
        cands, skill_mastery={}, question_count=99, rng=random.Random(0)
    )
    assert picked == [2, 3, 1]  # difficulty ascending, then id


def test_weighted_selection_skews_to_low_mastery_skilltags():
    weak = [Candidate(i, "easy", (1,)) for i in range(1, 11)]
    strong = [Candidate(i, "easy", (2,)) for i in range(11, 21)]
    weak_ids = {c.question_id for c in weak}

    # Averaged over several seeds so the assertion isn't pinned to one draw.
    totals = 0
    trials = 20
    for seed in range(trials):
        picked = select_mixed_questions(
            weak + strong,
            skill_mastery={1: 0.1, 2: 0.95},
            question_count=10,
            rng=random.Random(seed),
        )
        totals += sum(1 for q in picked if q in weak_ids)
    # 0.9 vs 0.05 weights — the low-mastery skill should dominate hard.
    assert totals / trials >= 8.0


def test_weighted_selection_respects_question_count():
    cands = [Candidate(i, "easy", (1,)) for i in range(1, 21)]
    picked = select_mixed_questions(
        cands,
        skill_mastery={1: 0.5},
        question_count=7,
        rng=random.Random(3),
    )
    assert len(picked) == 7
    assert len(set(picked)) == 7  # no repeats
    assert set(picked) <= {c.question_id for c in cands}


def test_empty_inputs_yield_an_empty_set():
    assert (
        select_mixed_questions(
            [], skill_mastery={}, question_count=10, rng=random.Random(0)
        )
        == []
    )
    assert (
        select_mixed_questions(
            [Candidate(1, "easy", ())],
            skill_mastery={},
            question_count=0,
            rng=random.Random(0),
        )
        == []
    )


# -- HTTP fixture --------------------------------------------------------


@pytest.fixture
def mixed_tree(db_session):
    """Year 7 → Mathematics → Unit "Number" with two published Topics and one
    draft. SkillTags: "weak" (many questions) and "strong" (many questions),
    plus a couple of untagged questions. A second Unit "Empty" carries nothing.
    """
    y7 = YearLevel(name="Year 7", syllabus_region="AU-NSW")
    db_session.add(y7)
    db_session.flush()
    maths = Subject(year_level_id=y7.id, title="Mathematics", order=1)
    db_session.add(maths)
    db_session.flush()

    number = Unit(subject_id=maths.id, title="Number", slug="number", order=1)
    empty = Unit(subject_id=maths.id, title="Empty", slug="empty", order=2)
    db_session.add_all([number, empty])
    db_session.flush()

    integers = Topic(
        unit_id=number.id, title="Integers", slug="integers", order=1
    )
    fractions = Topic(
        unit_id=number.id, title="Fractions", slug="fractions", order=2
    )
    draft = Topic(
        unit_id=number.id, title="Draft", slug="draft-topic", order=3
    )
    db_session.add_all([integers, fractions, draft])
    db_session.flush()

    db_session.add_all(
        [
            LectureContent(
                topic_id=integers.id, body="# I", status=CONTENT_PUBLISHED
            ),
            LectureContent(
                topic_id=fractions.id, body="# F", status=CONTENT_PUBLISHED
            ),
            LectureContent(
                topic_id=draft.id, body="# D", status=CONTENT_DRAFT
            ),
        ]
    )

    weak = SkillTag(name="weak skill")
    strong = SkillTag(name="strong skill")
    db_session.add_all([weak, strong])
    db_session.flush()

    def q(topic, tag, difficulty, n):
        row = Question(
            topic_id=topic.id,
            type="numeric",
            difficulty=difficulty,
            body=f"Question {n}?",
            answer_schema={"value": n, "tolerance": 0},
            worked_solution=f"It is {n}.",
        )
        if tag is not None:
            row.skill_tags.append(tag)
        return row

    weak_qs = [q(integers, weak, "easy", n) for n in range(1, 9)]
    strong_qs = [q(fractions, strong, "easy", n) for n in range(101, 109)]
    untagged_qs = [q(integers, None, "medium", n) for n in range(201, 204)]
    draft_q = q(draft, weak, "easy", 999)

    db_session.add_all(weak_qs + strong_qs + untagged_qs + [draft_q])
    db_session.commit()

    return {
        "year_level_id": y7.id,
        "number_unit_id": number.id,
        "empty_unit_id": empty.id,
        "weak_tag_id": weak.id,
        "strong_tag_id": strong.id,
        "weak_q_ids": [x.id for x in weak_qs],
        "strong_q_ids": [x.id for x in strong_qs],
        "untagged_q_ids": [x.id for x in untagged_qs],
        "draft_q_id": draft_q.id,
        "integers_topic_id": integers.id,
    }


def _student_id(db_session, email="ada@example.com"):
    return db_session.query(User).filter_by(email=email).one().id


def _start_mixed(client, headers, scope_type, scope_id, question_count=None):
    body = {"scope_type": scope_type, "scope_id": scope_id}
    if question_count is not None:
        body["question_count"] = question_count
    return client.post("/practice/mixed-sessions", json=body, headers=headers)


def _seed_snapshot(db_session, user_id, dimension, dimension_id, mastery):
    from datetime import datetime, timezone

    db_session.add(
        PerformanceSnapshot(
            user_id=user_id,
            dimension=dimension,
            dimension_id=dimension_id,
            mastery=mastery,
            trend="flat",
            sample_size=5,
            computed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    )
    db_session.commit()


# -- starting a mixed session -------------------------------------------


def test_start_persists_a_mixed_session_with_a_frozen_set(
    client, fake_email, db_session, mixed_tree
):
    headers = _student(client, fake_email)
    resp = _start_mixed(
        client, headers, "unit", mixed_tree["number_unit_id"]
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["mode"] == "mixed"
    assert body["scope_type"] == "unit"
    assert body["scope_label"] == "Number"
    assert len(body["questions"]) == DEFAULT_MIXED_QUESTION_COUNT

    session = (
        db_session.query(PracticeSession)
        .filter_by(user_id=_student_id(db_session))
        .one()
    )
    assert session.mode == PRACTICE_MODE_MIXED
    assert session.scope_type == PRACTICE_SCOPE_UNIT
    assert session.scope_id == mixed_tree["number_unit_id"]
    assert session.question_count == DEFAULT_MIXED_QUESTION_COUNT
    assert session.time_limit_seconds is None
    assert session.submitted_at is None

    frozen = (
        db_session.query(PracticeSessionQuestion)
        .filter_by(session_id=session.id)
        .order_by(PracticeSessionQuestion.position)
        .all()
    )
    assert [f.position for f in frozen] == list(range(DEFAULT_MIXED_QUESTION_COUNT))
    all_ids = set(
        mixed_tree["weak_q_ids"]
        + mixed_tree["strong_q_ids"]
        + mixed_tree["untagged_q_ids"]
    )
    assert {f.question_id for f in frozen} <= all_ids
    assert mixed_tree["draft_q_id"] not in {f.question_id for f in frozen}


def test_question_count_is_respected(client, fake_email, db_session, mixed_tree):
    headers = _student(client, fake_email)
    body = _start_mixed(
        client, headers, "unit", mixed_tree["number_unit_id"], question_count=5
    ).json()
    assert len(body["questions"]) == 5
    session = db_session.query(PracticeSession).one()
    assert session.question_count == 5


def test_cold_start_covers_both_skilltags_evenly(
    client, fake_email, mixed_tree
):
    headers = _student(client, fake_email)
    body = _start_mixed(
        client, headers, "unit", mixed_tree["number_unit_id"], question_count=6
    ).json()
    ids = {q["id"] for q in body["questions"]}
    weak = ids & set(mixed_tree["weak_q_ids"])
    strong = ids & set(mixed_tree["strong_q_ids"])
    # Even round-robin coverage: 3 from each tag.
    assert len(weak) == 3
    assert len(strong) == 3


def test_selection_skews_to_low_mastery_skilltags_with_snapshots(
    client, fake_email, db_session, mixed_tree
):
    headers = _student(client, fake_email)
    uid = _student_id(db_session)
    _seed_snapshot(
        db_session,
        uid,
        SNAPSHOT_DIMENSION_SKILL_TAG,
        mixed_tree["weak_tag_id"],
        0.1,
    )
    _seed_snapshot(
        db_session,
        uid,
        SNAPSHOT_DIMENSION_SKILL_TAG,
        mixed_tree["strong_tag_id"],
        0.95,
    )

    weak_seen = 0
    trials = 8
    for _ in range(trials):
        body = _start_mixed(
            client,
            headers,
            "unit",
            mixed_tree["number_unit_id"],
            question_count=6,
        ).json()
        ids = {q["id"] for q in body["questions"]}
        weak_seen += len(ids & set(mixed_tree["weak_q_ids"]))
    strong_total = trials * 6 - weak_seen
    assert weak_seen > strong_total


def test_cold_start_is_judged_per_scope_not_globally(
    client, fake_email, db_session, mixed_tree
):
    """A student with a snapshot for some *other* scope's SkillTag still gets
    even round-robin coverage for a Unit whose tags they've never touched."""
    headers = _student(client, fake_email)
    uid = _student_id(db_session)
    # A snapshot on an unrelated skill tag id (not in this unit).
    unrelated_tag = SkillTag(name="algebra basics")
    db_session.add(unrelated_tag)
    db_session.commit()
    _seed_snapshot(
        db_session, uid, SNAPSHOT_DIMENSION_SKILL_TAG, unrelated_tag.id, 0.2
    )
    # A topic snapshot too, to be sure only skill_tag rows in-scope matter.
    _seed_snapshot(
        db_session,
        uid,
        SNAPSHOT_DIMENSION_TOPIC,
        mixed_tree["integers_topic_id"],
        0.9,
    )

    body = _start_mixed(
        client, headers, "unit", mixed_tree["number_unit_id"], question_count=6
    ).json()
    ids = {q["id"] for q in body["questions"]}
    # Cold-start round-robin: exactly even across the two in-scope tags.
    assert len(ids & set(mixed_tree["weak_q_ids"])) == 3
    assert len(ids & set(mixed_tree["strong_q_ids"])) == 3


def test_immediate_feedback_and_attempt_linkage(
    client, fake_email, db_session, mixed_tree
):
    headers = _student(client, fake_email)
    body = _start_mixed(
        client, headers, "unit", mixed_tree["number_unit_id"]
    ).json()
    q = body["questions"][0]
    # The body carries the number we need for a correct answer ("Question N?").
    n = int(q["body"].split()[1].rstrip("?"))

    res = client.post(
        f"/practice/questions/{q['id']}/submit",
        json={"answer": n},
        headers=headers,
    ).json()
    # Not a withheld-feedback mode: correctness + worked solution come straight
    # back, exactly like Topic practice.
    assert res["is_correct"] is True
    assert res["worked_solution"] == f"It is {n}."

    session = db_session.query(PracticeSession).one()
    attempt = (
        db_session.query(QuestionAttempt)
        .filter_by(question_id=q["id"])
        .one()
    )
    assert attempt.practice_session_id == session.id
    assert attempt.after_time_limit is None


def test_year_level_scope_pulls_across_units(
    client, fake_email, db_session, mixed_tree
):
    headers = _student(client, fake_email)
    body = _start_mixed(
        client,
        headers,
        "year_level",
        mixed_tree["year_level_id"],
        question_count=4,
    ).json()
    assert body["scope_type"] == "year_level"
    assert body["scope_label"] == "Year 7"
    assert len(body["questions"]) == 4
    session = db_session.query(PracticeSession).one()
    assert session.scope_type == PRACTICE_SCOPE_YEAR_LEVEL


def test_payload_never_reveals_the_correct_answer(
    client, fake_email, mixed_tree
):
    headers = _student(client, fake_email)
    raw = _start_mixed(
        client, headers, "unit", mixed_tree["number_unit_id"]
    ).text
    for leak in ('"value"', "answer_schema", "worked_solution", "tolerance"):
        assert leak not in raw


def test_draft_questions_excluded_for_students_included_for_admin(
    client, fake_email, db_session, mixed_tree
):
    admin = _content_admin(client, fake_email, db_session)
    body = _start_mixed(
        client, admin, "unit", mixed_tree["number_unit_id"], question_count=50
    ).json()
    assert mixed_tree["draft_q_id"] in {q["id"] for q in body["questions"]}


def test_unknown_scope_is_404_and_empty_scope_is_400(
    client, fake_email, mixed_tree
):
    headers = _student(client, fake_email)
    assert (
        _start_mixed(client, headers, "unit", 999999).status_code == 404
    )
    assert (
        _start_mixed(
            client, headers, "unit", mixed_tree["empty_unit_id"]
        ).status_code
        == 400
    )


def test_bad_scope_type_is_422(client, fake_email, mixed_tree):
    headers = _student(client, fake_email)
    assert (
        _start_mixed(
            client, headers, "subject", mixed_tree["number_unit_id"]
        ).status_code
        == 422
    )


def test_mixed_endpoint_requires_authentication(client, mixed_tree):
    resp = client.post(
        "/practice/mixed-sessions",
        json={"scope_type": "unit", "scope_id": mixed_tree["number_unit_id"]},
    )
    assert resp.status_code == 401
