"""Practice & grading, exercised through the HTTP API.

A small fixture Topic with one question of each type is built directly in the DB
(the real seed-ingest core is ticket 05). Tests assert on responses and on the
`QuestionAttempt` rows the endpoints write — never on internals — and check that
no correct-answer data appears in the practice payload.
"""

from __future__ import annotations

import pytest

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
from tests.test_content import _content_admin, _student


@pytest.fixture
def practice_tree(db_session):
    """Year 7 → Mathematics → Number → "Integers" (published) with three
    questions: an mcq_single, an mcq_multi, and a numeric. A second Topic
    "Draft Topic" is draft-only and also carries a question.
    """
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
    draft = Topic(
        unit_id=number.id, title="Draft Topic", slug="draft-topic", order=2
    )
    db_session.add_all([integers, draft])
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
                topic_id=draft.id,
                body="# Draft",
                status=CONTENT_DRAFT,
                version=1,
            ),
        ]
    )

    adding = SkillTag(name="adding integers")
    ordering = SkillTag(name="ordering integers")
    db_session.add_all([adding, ordering])
    db_session.flush()

    single = Question(
        topic_id=integers.id,
        type="mcq_single",
        difficulty="easy",
        body=r"What is $-3 + 5$?",
        answer_schema={
            "options": [
                {"id": "a", "text": "-8"},
                {"id": "b", "text": "2"},
                {"id": "c", "text": "8"},
            ],
            "correct_option": "b",
        },
        worked_solution="Start at -3, count up 5: -2, -1, 0, 1, 2.",
    )
    multi = Question(
        topic_id=integers.id,
        type="mcq_multi",
        difficulty="medium",
        body="Which of these are negative?",
        answer_schema={
            "options": [
                {"id": "a", "text": "-4"},
                {"id": "b", "text": "0"},
                {"id": "c", "text": "-1"},
                {"id": "d", "text": "7"},
            ],
            "correct_options": ["a", "c"],
        },
        worked_solution="A number is negative when it is less than zero.",
    )
    numeric = Question(
        topic_id=integers.id,
        type="numeric",
        difficulty="hard",
        body=r"Evaluate $12 \div 7$ to two decimal places.",
        answer_schema={"value": 1.71, "tolerance": 0.01},
        worked_solution="12 / 7 = 1.714..., which rounds to 1.71.",
    )
    draft_q = Question(
        topic_id=draft.id,
        type="mcq_single",
        difficulty="easy",
        body="Hidden?",
        answer_schema={
            "options": [{"id": "a", "text": "yes"}],
            "correct_option": "a",
        },
        worked_solution="secret",
    )
    single.skill_tags.extend([adding, ordering])
    multi.skill_tags.append(ordering)
    db_session.add_all([single, multi, numeric, draft_q])
    db_session.commit()

    return {
        "single_id": single.id,
        "multi_id": multi.id,
        "numeric_id": numeric.id,
        "draft_question_id": draft_q.id,
    }


def _start(client, headers, slug="integers"):
    return client.post(
        "/practice/sessions", json={"topic_slug": slug}, headers=headers
    )


# -- starting a session ---------------------------------------------------


def test_session_returns_topic_questions_in_order_with_render_data(
    client, fake_email, practice_tree
):
    headers = _student(client, fake_email)
    resp = _start(client, headers)
    assert resp.status_code == 200
    body = resp.json()

    assert body["topic"]["slug"] == "integers"
    qs = body["questions"]
    assert [q["type"] for q in qs] == ["mcq_single", "mcq_multi", "numeric"]
    assert [q["difficulty"] for q in qs] == ["easy", "medium", "hard"]
    assert "-3 + 5" in qs[0]["body"]

    # MCQ options carry id + text only; numeric has no options.
    assert [o["id"] for o in qs[0]["options"]] == ["a", "b", "c"]
    assert {o["text"] for o in qs[0]["options"]} == {"-8", "2", "8"}
    assert qs[2]["options"] is None

    # The payload is scoped to body / difficulty / options — nothing else.
    assert set(qs[0].keys()) == {"id", "type", "difficulty", "body", "options"}


def test_practice_payload_never_reveals_the_correct_answer(
    client, fake_email, practice_tree
):
    headers = _student(client, fake_email)
    raw = _start(client, headers).text

    for leak in (
        "correct_option",
        "correct_options",
        "answer_schema",
        "worked_solution",
        "tolerance",
        '"value"',
    ):
        assert leak not in raw

    # And nothing in a rendered option object beyond id/text.
    for q in _start(client, headers).json()["questions"]:
        for opt in q["options"] or []:
            assert set(opt.keys()) == {"id", "text"}


def test_student_cannot_start_a_session_on_a_draft_topic(
    client, fake_email, practice_tree
):
    headers = _student(client, fake_email)
    assert _start(client, headers, slug="draft-topic").status_code == 404


def test_content_admin_can_start_a_session_on_a_draft_topic(
    client, fake_email, db_session, practice_tree
):
    headers = _content_admin(client, fake_email, db_session)
    resp = _start(client, headers, slug="draft-topic")
    assert resp.status_code == 200
    assert len(resp.json()["questions"]) == 1


def test_start_session_on_unknown_topic_is_404(client, fake_email, practice_tree):
    headers = _student(client, fake_email)
    assert _start(client, headers, slug="nope").status_code == 404


# -- submitting: mcq_single --------------------------------------------------


def test_mcq_single_correct_and_incorrect(client, fake_email, practice_tree):
    headers = _student(client, fake_email)
    qid = practice_tree["single_id"]

    good = client.post(
        f"/practice/questions/{qid}/submit",
        json={"answer": "b", "time_taken": 12},
        headers=headers,
    ).json()
    assert good["is_correct"] is True
    assert good["attempt_no"] == 1
    assert "count up 5" in good["worked_solution"]

    bad = client.post(
        f"/practice/questions/{qid}/submit",
        json={"answer": "a"},
        headers=headers,
    ).json()
    assert bad["is_correct"] is False
    assert bad["attempt_no"] == 2
    # Worked solution comes back regardless of correctness.
    assert bad["worked_solution"] == good["worked_solution"]


# -- submitting: mcq_multi -------------------------------------------------


def test_mcq_multi_requires_the_exact_set(client, fake_email, practice_tree):
    headers = _student(client, fake_email)
    qid = practice_tree["multi_id"]

    def submit(answer):
        return client.post(
            f"/practice/questions/{qid}/submit",
            json={"answer": answer},
            headers=headers,
        ).json()["is_correct"]

    assert submit(["a", "c"]) is True
    assert submit(["c", "a"]) is True
    assert submit(["a"]) is False
    assert submit(["a", "c", "d"]) is False


# -- submitting: numeric (tolerance boundary) ----------------------------


def test_numeric_inside_and_outside_tolerance(
    client, fake_email, practice_tree
):
    headers = _student(client, fake_email)
    qid = practice_tree["numeric_id"]

    def submit(answer):
        return client.post(
            f"/practice/questions/{qid}/submit",
            json={"answer": answer},
            headers=headers,
        ).json()["is_correct"]

    assert submit(1.71) is True
    assert submit(1.72) is True  # exactly on the tolerance edge
    assert submit(1.70) is True
    assert submit(1.7201) is False  # just outside
    assert submit(1.6899) is False


# -- persisted attempt rows --------------------------------------------------


def test_each_submission_persists_attempt_no_time_taken_and_correctness(
    client, fake_email, db_session, practice_tree
):
    headers = _student(client, fake_email)
    qid = practice_tree["single_id"]
    student_id = (
        db_session.query(User).filter_by(email="ada@example.com").one().id
    )

    client.post(
        f"/practice/questions/{qid}/submit",
        json={"answer": "a", "time_taken": 30},
        headers=headers,
    )
    client.post(
        f"/practice/questions/{qid}/submit",
        json={"answer": "b", "time_taken": 9},
        headers=headers,
    )

    rows = (
        db_session.query(QuestionAttempt)
        .filter_by(user_id=student_id, question_id=qid)
        .order_by(QuestionAttempt.attempt_no)
        .all()
    )
    assert [r.attempt_no for r in rows] == [1, 2]
    assert [r.is_correct for r in rows] == [False, True]
    assert [r.time_taken for r in rows] == [30, 9]
    assert [r.submitted_answer for r in rows] == ["a", "b"]
    assert all(r.solution_viewed is False for r in rows)
    assert all(r.created_at is not None for r in rows)


# -- show solution -----------------------------------------------------


def test_show_solution_marks_the_latest_attempt_and_returns_the_solution(
    client, fake_email, db_session, practice_tree
):
    headers = _student(client, fake_email)
    qid = practice_tree["numeric_id"]

    client.post(
        f"/practice/questions/{qid}/submit",
        json={"answer": 1.0},
        headers=headers,
    )
    resp = client.post(
        f"/practice/questions/{qid}/show-solution", headers=headers
    )
    assert resp.status_code == 200
    assert "rounds to 1.71" in resp.json()["worked_solution"]

    rows = db_session.query(QuestionAttempt).filter_by(question_id=qid).all()
    assert len(rows) == 1
    assert rows[0].solution_viewed is True
    assert rows[0].attempt_no == 1  # no extra row created


def test_show_solution_before_any_submission_writes_a_marker_row(
    client, fake_email, db_session, practice_tree
):
    headers = _student(client, fake_email)
    qid = practice_tree["single_id"]

    resp = client.post(
        f"/practice/questions/{qid}/show-solution", headers=headers
    )
    assert resp.status_code == 200

    rows = db_session.query(QuestionAttempt).filter_by(question_id=qid).all()
    assert len(rows) == 1
    marker = rows[0]
    assert marker.solution_viewed is True
    assert marker.attempt_no == 0
    assert marker.submitted_answer is None
    assert marker.is_correct is None

    # A later real submission is attempt_no 1, not 2 — the marker doesn't count.
    after = client.post(
        f"/practice/questions/{qid}/submit",
        json={"answer": "b"},
        headers=headers,
    ).json()
    assert after["attempt_no"] == 1


# -- solution_reveal_after_attempts Setting ---------------------------------


def test_worked_solution_comes_back_from_the_first_submission_by_default(
    client, fake_email, practice_tree
):
    headers = _student(client, fake_email)
    qid = practice_tree["numeric_id"]

    first = client.post(
        f"/practice/questions/{qid}/submit",
        json={"answer": 0.0},
        headers=headers,
    ).json()
    assert first["worked_solution"] == "12 / 7 = 1.714..., which rounds to 1.71."


def test_setting_defers_the_worked_solution_in_the_submit_response(
    client, fake_email, db_session, practice_tree
):
    from app.models import Setting
    from app.practice.settings import SETTING_SOLUTION_REVEAL_AFTER_ATTEMPTS

    db_session.add(
        Setting(key=SETTING_SOLUTION_REVEAL_AFTER_ATTEMPTS, value="2")
    )
    db_session.commit()

    headers = _student(client, fake_email)
    qid = practice_tree["numeric_id"]

    first = client.post(
        f"/practice/questions/{qid}/submit",
        json={"answer": 0.0},
        headers=headers,
    ).json()
    assert first["attempt_no"] == 1
    assert first["worked_solution"] is None

    second = client.post(
        f"/practice/questions/{qid}/submit",
        json={"answer": 0.0},
        headers=headers,
    ).json()
    assert second["attempt_no"] == 2
    assert second["worked_solution"] == (
        "12 / 7 = 1.714..., which rounds to 1.71."
    )

    # The explicit "show solution" request is never gated by the Setting.
    shown = client.post(
        f"/practice/questions/{qid}/show-solution", headers=headers
    ).json()
    assert shown["worked_solution"] == (
        "12 / 7 = 1.714..., which rounds to 1.71."
    )


def test_submitting_to_a_draft_topics_question_is_404_for_a_student(
    client, fake_email, practice_tree
):
    headers = _student(client, fake_email)
    qid = practice_tree["draft_question_id"]
    assert (
        client.post(
            f"/practice/questions/{qid}/submit",
            json={"answer": "a"},
            headers=headers,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/practice/questions/{qid}/show-solution", headers=headers
        ).status_code
        == 404
    )


def test_submitting_to_an_unknown_question_is_404(
    client, fake_email, practice_tree
):
    headers = _student(client, fake_email)
    assert (
        client.post(
            "/practice/questions/999999/submit",
            json={"answer": "a"},
            headers=headers,
        ).status_code
        == 404
    )


# -- auth gate ----------------------------------------------------------


def test_practice_endpoints_require_authentication(client, practice_tree):
    assert (
        client.post(
            "/practice/sessions", json={"topic_slug": "integers"}
        ).status_code
        == 401
    )
    assert (
        client.post("/practice/questions/1/submit", json={"answer": "a"}).status_code
        == 401
    )
    assert (
        client.post("/practice/questions/1/show-solution").status_code == 401
    )
