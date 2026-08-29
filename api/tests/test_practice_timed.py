"""Timed quiz mode — the pure time arithmetic and the HTTP flow.

The `FakeClock` is advanced across the quiz's limit to prove expiry is
server-authoritative: the countdown, the late-answer flag, and unanswered
scoring are all derived from `started_at` + the clock, never trusted from the
client. Feedback is withheld until the whole set is submitted for review.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models import (
    CONTENT_DRAFT,
    CONTENT_PUBLISHED,
    PRACTICE_MODE_TIMED,
    PRACTICE_MODE_TOPIC,
    PRACTICE_SCOPE_TOPIC,
    PRACTICE_SCOPE_UNIT,
    LectureContent,
    PracticeSession,
    PracticeSessionQuestion,
    Question,
    QuestionAttempt,
    Subject,
    Topic,
    Unit,
    User,
    YearLevel,
)
from app.practice.timed import Countdown, proportion_correct, total_time_limit
from tests.test_auth import login, register_and_verify
from tests.test_content import _student

START = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


# -- pure helpers -------------------------------------------------------------


def test_total_time_limit_fills_gaps_with_the_default():
    assert total_time_limit([30, None, 60, None], 90) == 30 + 90 + 60 + 90


def test_total_time_limit_of_an_empty_set_is_zero():
    assert total_time_limit([], 90) == 0


def test_countdown_remaining_counts_down_and_never_goes_negative():
    cd = Countdown(180, START)
    assert cd.remaining(START) == 180
    assert cd.remaining(START + timedelta(seconds=100)) == 80
    assert cd.remaining(START + timedelta(seconds=999)) == 0


def test_countdown_is_after_limit_only_once_the_limit_has_elapsed():
    cd = Countdown(180, START)
    assert not cd.is_after_limit(START)
    assert not cd.is_after_limit(START + timedelta(seconds=180))
    assert cd.is_after_limit(START + timedelta(seconds=181))


def test_proportion_correct_over_the_vector():
    assert proportion_correct([True, True, False, False]) == 0.5
    assert proportion_correct([True, True, True]) == 1.0
    assert proportion_correct([False, False]) == 0.0
    assert proportion_correct([]) == 0.0


# -- fixture ----------------------------------------------------------------


@pytest.fixture
def timed_tree(db_session):
    """Year 7 → Mathematics → Unit "Number" with two published Topics and one
    draft. Visible questions, in order: q1 (est 30), q2 (no est → default), q3
    (est 60). A second Unit "Empty" carries nothing.
    """
    y7 = YearLevel(name="Year 7", syllabus_region="AU-NSW")
    db_session.add(y7)
    db_session.flush()
    maths = Subject(year_level_id=y7.id, title="Mathematics", order=1)
    db_session.add(maths)
    db_session.flush()

    number = Unit(
        subject_id=maths.id, title="Number", slug="number", order=1
    )
    empty = Unit(
        subject_id=maths.id, title="Empty", slug="empty", order=2
    )
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
                topic_id=integers.id,
                body="# Integers",
                status=CONTENT_PUBLISHED,
                version=1,
            ),
            LectureContent(
                topic_id=fractions.id,
                body="# Fractions",
                status=CONTENT_PUBLISHED,
                version=1,
            ),
            LectureContent(
                topic_id=draft.id,
                body="# Draft",
                status=CONTENT_DRAFT,
                version=1,
            ),
        ]
    )

    q1 = Question(
        topic_id=integers.id,
        type="mcq_single",
        difficulty="easy",
        body="What is $-3 + 5$?",
        answer_schema={
            "options": [
                {"id": "a", "text": "-8"},
                {"id": "b", "text": "2"},
            ],
            "correct_option": "b",
        },
        worked_solution="Count up 5 from -3.",
        estimated_time_seconds=30,
    )
    q2 = Question(
        topic_id=integers.id,
        type="numeric",
        difficulty="medium",
        body="Evaluate $10 / 2$.",
        answer_schema={"value": 5, "tolerance": 0},
        worked_solution="10 / 2 = 5.",
        estimated_time_seconds=None,
    )
    q3 = Question(
        topic_id=fractions.id,
        type="mcq_single",
        difficulty="hard",
        body=r"Which is larger, $\tfrac12$ or $\tfrac13$?",
        answer_schema={
            "options": [
                {"id": "a", "text": "one half"},
                {"id": "b", "text": "one third"},
            ],
            "correct_option": "a",
        },
        worked_solution="Halves are bigger than thirds.",
        estimated_time_seconds=60,
    )
    draft_q = Question(
        topic_id=draft.id,
        type="numeric",
        difficulty="easy",
        body="Hidden?",
        answer_schema={"value": 1, "tolerance": 0},
        worked_solution="secret",
        estimated_time_seconds=999,
    )
    db_session.add_all([q1, q2, q3, draft_q])
    db_session.commit()

    return {
        "number_unit_id": number.id,
        "empty_unit_id": empty.id,
        "q1_id": q1.id,
        "q2_id": q2.id,
        "q3_id": q3.id,
    }


def _second_student(client, fake_email):
    creds = register_and_verify(
        client, fake_email, email="bob@example.com", name="Bob Bobson"
    )
    token = login(client, creds).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _start(client, headers, unit_id):
    return client.post(
        "/practice/timed-sessions", json={"unit_id": unit_id}, headers=headers
    )


def _submit(client, headers, qid, answer):
    return client.post(
        f"/practice/questions/{qid}/submit",
        json={"answer": answer},
        headers=headers,
    )


def _student_id(db_session, email="ada@example.com"):
    return db_session.query(User).filter_by(email=email).one().id


# -- starting a quiz -------------------------------------------------------


def test_start_sets_the_limit_from_estimated_times_and_the_clock(
    client, fake_email, fake_clock, db_session, timed_tree
):
    fake_clock.set(START)
    headers = _student(client, fake_email)

    resp = _start(client, headers, timed_tree["number_unit_id"])
    assert resp.status_code == 200
    body = resp.json()

    # 30 + (default 90) + 60
    assert body["time_limit_seconds"] == 180
    assert body["remaining_seconds"] == 180
    assert body["mode"] == "timed"
    assert body["scope_type"] == "unit"
    assert body["unit"]["title"] == "Number"
    assert [q["id"] for q in body["questions"]] == [
        timed_tree["q1_id"],
        timed_tree["q2_id"],
        timed_tree["q3_id"],
    ]

    session = (
        db_session.query(PracticeSession)
        .filter_by(user_id=_student_id(db_session))
        .one()
    )
    assert session.mode == PRACTICE_MODE_TIMED
    assert session.scope_type == PRACTICE_SCOPE_UNIT
    assert session.scope_id == timed_tree["number_unit_id"]
    assert session.question_count == 3
    assert session.time_limit_seconds == 180
    assert session.started_at == START
    assert session.submitted_at is None
    assert session.score is None

    frozen = (
        db_session.query(PracticeSessionQuestion)
        .filter_by(session_id=session.id)
        .order_by(PracticeSessionQuestion.position)
        .all()
    )
    assert [f.position for f in frozen] == [0, 1, 2]


def test_start_uses_the_default_question_seconds_setting_for_gaps(
    client, fake_email, db_session, timed_tree
):
    from app.practice.settings import SETTING_DEFAULT_QUESTION_SECONDS
    from app.settings_store import write_setting

    write_setting(db_session, SETTING_DEFAULT_QUESTION_SECONDS, "20")
    db_session.commit()

    headers = _student(client, fake_email)
    body = _start(client, headers, timed_tree["number_unit_id"]).json()
    # 30 + (setting 20) + 60
    assert body["time_limit_seconds"] == 110


def test_start_excludes_draft_topic_questions(
    client, fake_email, timed_tree
):
    headers = _student(client, fake_email)
    body = _start(client, headers, timed_tree["number_unit_id"]).json()
    assert len(body["questions"]) == 3  # the draft topic's question is not here


def test_start_on_a_unit_with_no_questions_is_400(
    client, fake_email, timed_tree
):
    headers = _student(client, fake_email)
    resp = _start(client, headers, timed_tree["empty_unit_id"])
    assert resp.status_code == 400


def test_start_on_an_unknown_unit_is_404(client, fake_email, timed_tree):
    headers = _student(client, fake_email)
    assert _start(client, headers, 999999).status_code == 404


def test_each_retake_is_a_new_independent_session(
    client, fake_email, db_session, timed_tree
):
    headers = _student(client, fake_email)
    a = _start(client, headers, timed_tree["number_unit_id"]).json()
    b = _start(client, headers, timed_tree["number_unit_id"]).json()
    c = _start(client, headers, timed_tree["number_unit_id"]).json()

    ids = {a["session_id"], b["session_id"], c["session_id"]}
    assert len(ids) == 3
    assert (
        db_session.query(PracticeSession)
        .filter_by(user_id=_student_id(db_session))
        .count()
        == 3
    )


# -- feedback withheld while open ----------------------------------------


def test_feedback_is_withheld_while_the_quiz_is_open(
    client, fake_email, timed_tree
):
    headers = _student(client, fake_email)
    _start(client, headers, timed_tree["number_unit_id"])

    res = _submit(client, headers, timed_tree["q1_id"], "b").json()
    assert res["is_correct"] is None
    assert res["worked_solution"] is None
    assert res["after_time_limit"] is False
    assert res["attempt_no"] == 1


def test_show_solution_is_blocked_while_the_quiz_is_open(
    client, fake_email, timed_tree
):
    headers = _student(client, fake_email)
    _start(client, headers, timed_tree["number_unit_id"])
    resp = client.post(
        f"/practice/questions/{timed_tree['q1_id']}/show-solution",
        headers=headers,
    )
    assert resp.status_code == 409


def test_answer_is_still_graded_and_persisted_while_feedback_is_withheld(
    client, fake_email, db_session, timed_tree
):
    headers = _student(client, fake_email)
    _start(client, headers, timed_tree["number_unit_id"])
    _submit(client, headers, timed_tree["q1_id"], "b")  # correct
    _submit(client, headers, timed_tree["q2_id"], 999)  # wrong

    rows = (
        db_session.query(QuestionAttempt)
        .filter_by(user_id=_student_id(db_session))
        .order_by(QuestionAttempt.question_id)
        .all()
    )
    by_q = {r.question_id: r for r in rows}
    assert by_q[timed_tree["q1_id"]].is_correct is True
    assert by_q[timed_tree["q2_id"]].is_correct is False
    # Linked to the timed session, and flagged as within-time.
    session = db_session.query(PracticeSession).one()
    assert all(r.practice_session_id == session.id for r in rows)
    assert all(r.after_time_limit is False for r in rows)


# -- expiry is server-authoritative -----------------------------------


def test_get_session_countdown_is_derived_from_the_clock(
    client, fake_email, fake_clock, timed_tree
):
    fake_clock.set(START)
    headers = _student(client, fake_email)
    sid = _start(client, headers, timed_tree["number_unit_id"]).json()[
        "session_id"
    ]

    fake_clock.advance(timedelta(seconds=100))
    body = client.get(
        f"/practice/sessions/{sid}", headers=headers
    ).json()
    assert body["remaining_seconds"] == 80

    fake_clock.advance(timedelta(seconds=50))
    body = client.get(
        f"/practice/sessions/{sid}", headers=headers
    ).json()
    assert body["remaining_seconds"] == 30


def test_observing_an_expired_session_closes_it_server_side(
    client, fake_email, fake_clock, db_session, timed_tree
):
    """A student who abandons the tab: nothing calls submit, but the next
    observation of the run finalises it — score and submitted_at exist."""
    fake_clock.set(START)
    headers = _student(client, fake_email)
    sid = _start(client, headers, timed_tree["number_unit_id"]).json()[
        "session_id"
    ]
    _submit(client, headers, timed_tree["q1_id"], "b")  # 1 of 3 correct

    fake_clock.advance(timedelta(seconds=181))  # countdown exhausted
    body = client.get(
        f"/practice/sessions/{sid}", headers=headers
    ).json()

    assert body["remaining_seconds"] == 0
    assert body["submitted_at"] is not None
    assert body["review"] is not None
    assert body["review"]["score"] == pytest.approx(1 / 3, rel=1e-3)

    session = db_session.query(PracticeSession).one()
    assert session.submitted_at == START + timedelta(seconds=181)
    assert session.score == pytest.approx(1 / 3, rel=1e-3)


def test_withholding_survives_a_newer_topic_session_on_a_shared_question(
    client, fake_email, timed_tree
):
    """A topic-practice run started after the quiz (another tab) has a higher
    id, but the quiz still owns every submit of a question it froze."""
    headers = _student(client, fake_email)
    _start(client, headers, timed_tree["number_unit_id"])
    # A topic session over "Integers" — freezes q1 and q2, newer id.
    assert (
        client.post(
            "/practice/sessions",
            json={"topic_slug": "integers"},
            headers=headers,
        ).status_code
        == 200
    )

    res = _submit(client, headers, timed_tree["q1_id"], "b").json()
    assert res["is_correct"] is None  # still withheld
    assert res["worked_solution"] is None


def test_late_answer_is_accepted_and_flagged(
    client, fake_email, fake_clock, db_session, timed_tree
):
    fake_clock.set(START)
    headers = _student(client, fake_email)
    _start(client, headers, timed_tree["number_unit_id"])

    fake_clock.advance(timedelta(seconds=181))  # just past the 180s limit
    res = _submit(client, headers, timed_tree["q1_id"], "b")
    assert res.status_code == 200
    assert res.json()["after_time_limit"] is True

    row = (
        db_session.query(QuestionAttempt)
        .filter_by(question_id=timed_tree["q1_id"])
        .one()
    )
    assert row.after_time_limit is True
    assert row.is_correct is True  # still graded


# -- submitting the quiz -------------------------------------------------


def test_submit_scores_unanswered_as_incorrect_and_sets_fields(
    client, fake_email, fake_clock, db_session, timed_tree
):
    fake_clock.set(START)
    headers = _student(client, fake_email)
    sid = _start(client, headers, timed_tree["number_unit_id"]).json()[
        "session_id"
    ]

    _submit(client, headers, timed_tree["q1_id"], "b")  # correct
    _submit(client, headers, timed_tree["q2_id"], 999)  # wrong
    # q3 left unanswered

    fake_clock.advance(timedelta(seconds=200))
    review = client.post(
        f"/practice/sessions/{sid}/submit", headers=headers
    ).json()

    assert review["score"] == pytest.approx(1 / 3, rel=1e-3)
    assert review["question_count"] == 3

    session = db_session.query(PracticeSession).one()
    assert session.score == pytest.approx(1 / 3, rel=1e-3)
    assert session.submitted_at == START + timedelta(seconds=200)


def test_review_returns_per_question_correctness_and_worked_solutions(
    client, fake_email, timed_tree
):
    headers = _student(client, fake_email)
    sid = _start(client, headers, timed_tree["number_unit_id"]).json()[
        "session_id"
    ]
    _submit(client, headers, timed_tree["q1_id"], "b")  # correct
    _submit(client, headers, timed_tree["q3_id"], "b")  # wrong

    review = client.post(
        f"/practice/sessions/{sid}/submit", headers=headers
    ).json()
    by_id = {q["question"]["id"]: q for q in review["questions"]}

    assert by_id[timed_tree["q1_id"]]["is_correct"] is True
    assert by_id[timed_tree["q1_id"]]["submitted_answer"] == "b"
    assert (
        by_id[timed_tree["q1_id"]]["worked_solution"]
        == "Count up 5 from -3."
    )
    assert by_id[timed_tree["q3_id"]]["is_correct"] is False
    # Unanswered → null correctness, but the worked solution is still there.
    assert by_id[timed_tree["q2_id"]]["is_correct"] is None
    assert by_id[timed_tree["q2_id"]]["submitted_answer"] is None
    assert by_id[timed_tree["q2_id"]]["worked_solution"] == "10 / 2 = 5."


def test_submit_is_idempotent_across_a_manual_and_auto_submit_race(
    client, fake_email, fake_clock, db_session, timed_tree
):
    fake_clock.set(START)
    headers = _student(client, fake_email)
    sid = _start(client, headers, timed_tree["number_unit_id"]).json()[
        "session_id"
    ]
    _submit(client, headers, timed_tree["q1_id"], "b")

    fake_clock.advance(timedelta(seconds=200))
    first = client.post(
        f"/practice/sessions/{sid}/submit", headers=headers
    ).json()
    fake_clock.advance(timedelta(seconds=50))
    second = client.post(
        f"/practice/sessions/{sid}/submit", headers=headers
    ).json()

    assert first["score"] == second["score"]
    session = db_session.query(PracticeSession).one()
    # submitted_at stamped once, at the first submit.
    assert session.submitted_at == START + timedelta(seconds=200)


def test_get_session_returns_the_review_once_submitted(
    client, fake_email, timed_tree
):
    headers = _student(client, fake_email)
    sid = _start(client, headers, timed_tree["number_unit_id"]).json()[
        "session_id"
    ]
    _submit(client, headers, timed_tree["q1_id"], "b")
    client.post(f"/practice/sessions/{sid}/submit", headers=headers)

    body = client.get(
        f"/practice/sessions/{sid}", headers=headers
    ).json()
    assert body["submitted_at"] is not None
    assert body["review"] is not None
    assert body["questions"] == []


def test_open_session_get_restores_answers_so_far(
    client, fake_email, timed_tree
):
    headers = _student(client, fake_email)
    sid = _start(client, headers, timed_tree["number_unit_id"]).json()[
        "session_id"
    ]
    _submit(client, headers, timed_tree["q1_id"], "b")

    body = client.get(
        f"/practice/sessions/{sid}", headers=headers
    ).json()
    assert body["review"] is None
    assert body["answers"] == [
        {
            "question_id": timed_tree["q1_id"],
            "submitted_answer": "b",
            "after_time_limit": False,
        }
    ]


# -- isolation & auth --------------------------------------------------


def test_get_session_is_404_for_another_student(
    client, fake_email, timed_tree
):
    owner = _student(client, fake_email)
    sid = _start(client, owner, timed_tree["number_unit_id"]).json()[
        "session_id"
    ]

    other = _second_student(client, fake_email)
    assert (
        client.get(
            f"/practice/sessions/{sid}", headers=other
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/practice/sessions/{sid}/submit", headers=other
        ).status_code
        == 404
    )


def test_non_timed_session_is_404_on_the_timed_endpoints(
    client, fake_email, db_session, timed_tree
):
    headers = _student(client, fake_email)
    # A bare topic-mode session (mode != timed).
    topic = db_session.query(Topic).filter_by(slug="integers").one()
    session = PracticeSession(
        user_id=_student_id(db_session),
        mode=PRACTICE_MODE_TOPIC,
        scope_type=PRACTICE_SCOPE_TOPIC,
        scope_id=topic.id,
        question_count=0,
        started_at=START,
    )
    db_session.add(session)
    db_session.commit()

    assert (
        client.get(
            f"/practice/sessions/{session.id}", headers=headers
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/practice/sessions/{session.id}/submit", headers=headers
        ).status_code
        == 404
    )


def test_timed_endpoints_require_authentication(client, timed_tree):
    assert (
        client.post(
            "/practice/timed-sessions",
            json={"unit_id": timed_tree["number_unit_id"]},
        ).status_code
        == 401
    )
    assert client.get("/practice/sessions/1").status_code == 401
    assert client.post("/practice/sessions/1/submit").status_code == 401


# -- non-timed practice is unaffected -------------------------------------


def test_topic_practice_submit_still_returns_feedback(
    client, fake_email, db_session, timed_tree
):
    """A submit outside any timed quiz is unchanged: correctness and the
    worked solution come straight back."""
    headers = _student(client, fake_email)
    res = _submit(client, headers, timed_tree["q1_id"], "b").json()
    assert res["is_correct"] is True
    assert res["worked_solution"] == "Count up 5 from -3."
    assert res["after_time_limit"] is False

    row = (
        db_session.query(QuestionAttempt)
        .filter_by(question_id=timed_tree["q1_id"])
        .one()
    )
    assert row.after_time_limit is None
