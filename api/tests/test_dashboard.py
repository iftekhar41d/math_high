"""The student dashboard, exercised end to end through the HTTP API.

Every signal on the dashboard is produced the way a real student produces it:
attempts via `POST /practice/...`, lecture views via `GET /content/topics/...`,
and MentisQ usage via `POST /mentisq/messages`. Tests then assert the dashboard
reflects exactly what was done.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.models import (
    CONTENT_DRAFT,
    CONTENT_PUBLISHED,
    LectureContent,
    Question,
    Subject,
    Topic,
    Unit,
    YearLevel,
)
from tests.test_auth import REGISTER, login, register_and_verify
from tests.test_content import _student


def _relogin(client, creds=REGISTER):
    """A fresh access token — used after advancing the fake clock past the
    short access-token TTL."""
    token = login(client, creds).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _other_student(client, fake_email, *, email, name):
    creds = register_and_verify(client, fake_email, email=email, name=name)
    token = login(client, creds).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def tree(db_session):
    """Year 7 -> Mathematics -> Number with two published Topics — "Integers"
    (two questions) and "Fractions" (one question) — plus a draft Topic.
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
    fractions = Topic(
        unit_id=number.id, title="Fractions", slug="fractions", order=2
    )
    draft = Topic(
        unit_id=number.id, title="Draft Topic", slug="draft-topic", order=3
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

    int_a = Question(
        topic_id=integers.id,
        type="mcq_single",
        difficulty="easy",
        body=r"What is $-3 + 5$?",
        answer_schema={
            "options": [
                {"id": "a", "text": "-8"},
                {"id": "b", "text": "2"},
            ],
            "correct_option": "b",
        },
        worked_solution="Count up 5 from -3.",
    )
    int_b = Question(
        topic_id=integers.id,
        type="numeric",
        difficulty="medium",
        body=r"Evaluate $12 \div 7$ to 2 dp.",
        answer_schema={"value": 1.71, "tolerance": 0.01},
        worked_solution="1.714... rounds to 1.71.",
    )
    frac_a = Question(
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
    )
    db_session.add_all([int_a, int_b, frac_a])
    db_session.commit()

    return {
        "int_a": int_a.id,
        "int_b": int_b.id,
        "frac_a": frac_a.id,
    }


def _submit(client, headers, qid, answer, time_taken=None):
    return client.post(
        f"/practice/questions/{qid}/submit",
        json={"answer": answer, "time_taken": time_taken},
        headers=headers,
    )


# -- auth gate ----------------------------------------------------------------


def test_dashboard_requires_authentication(client, tree):
    assert client.get("/dashboard").status_code == 401


# -- empty state ------------------------------------------------------------


def test_new_student_dashboard_is_empty(client, fake_email, tree):
    headers = _student(client, fake_email)
    body = client.get("/dashboard", headers=headers).json()

    assert body["recent_attempts"] == []
    assert body["topic_performance"] == []
    assert body["activity"] == {
        "window_days": 30,
        "topic_views": 0,
        "topics_viewed": 0,
        "mentisq_messages": 0,
    }


# -- recent attempts ------------------------------------------------------


def test_recent_attempts_list_attempts_newest_first(
    client, fake_email, fake_clock, tree
):
    headers = _student(client, fake_email)

    _submit(client, headers, tree["int_a"], "a", time_taken=20)  # wrong
    fake_clock.advance(timedelta(minutes=1))
    _submit(client, headers, tree["int_a"], "b", time_taken=8)  # right, attempt 2
    fake_clock.advance(timedelta(minutes=1))
    _submit(client, headers, tree["frac_a"], "a")  # right

    attempts = client.get("/dashboard", headers=headers).json()[
        "recent_attempts"
    ]
    assert [a["question_id"] for a in attempts] == [
        tree["frac_a"],
        tree["int_a"],
        tree["int_a"],
    ]
    assert [a["is_correct"] for a in attempts] == [True, True, False]
    assert [a["attempt_no"] for a in attempts] == [1, 2, 1]
    assert [a["topic_title"] for a in attempts] == [
        "Fractions",
        "Integers",
        "Integers",
    ]
    assert attempts[1]["time_taken"] == 8
    assert attempts[0]["difficulty"] == "hard"


def test_solution_only_marker_rows_are_not_attempts(
    client, fake_email, tree
):
    headers = _student(client, fake_email)

    # No submission — just reveal the solution. Writes an attempt_no=0 marker.
    client.post(
        f"/practice/questions/{tree['int_a']}/show-solution", headers=headers
    )

    body = client.get("/dashboard", headers=headers).json()
    assert body["recent_attempts"] == []
    assert body["topic_performance"] == []


# -- per-Topic percentage correct ---------------------------------------


def test_per_topic_percentage_matches_the_attempts(
    client, fake_email, tree
):
    headers = _student(client, fake_email)

    # Integers: 3 graded attempts, 2 correct -> 66.7%
    _submit(client, headers, tree["int_a"], "b")  # correct
    _submit(client, headers, tree["int_a"], "a")  # wrong
    _submit(client, headers, tree["int_b"], 1.71)  # correct
    # Fractions: 1 graded attempt, 0 correct -> 0.0%
    _submit(client, headers, tree["frac_a"], "b")  # wrong

    perf = client.get("/dashboard", headers=headers).json()[
        "topic_performance"
    ]
    # Ordered by Topic title.
    assert [p["topic_slug"] for p in perf] == ["fractions", "integers"]
    assert perf[0] == {
        "topic_slug": "fractions",
        "topic_title": "Fractions",
        "attempts": 1,
        "correct": 0,
        "percent_correct": 0.0,
    }
    assert perf[1] == {
        "topic_slug": "integers",
        "topic_title": "Integers",
        "attempts": 3,
        "correct": 2,
        "percent_correct": 66.7,
    }


# -- activity window ----------------------------------------------------


def test_activity_counts_topic_views_and_mentisq_messages(
    client, fake_email, tree
):
    headers = _student(client, fake_email)

    # Two views of Integers, one of Fractions -> 3 views across 2 Topics.
    client.get("/content/topics/integers", headers=headers)
    client.get("/content/topics/integers", headers=headers)
    client.get("/content/topics/fractions", headers=headers)

    client.post(
        "/mentisq/messages",
        json={"content": "How do I add negatives?"},
        headers=headers,
    )
    client.post(
        "/mentisq/messages",
        json={"content": "And subtract them?"},
        headers=headers,
    )

    activity = client.get("/dashboard", headers=headers).json()["activity"]
    assert activity["topic_views"] == 3
    assert activity["topics_viewed"] == 2
    assert activity["mentisq_messages"] == 2


def test_activity_ignores_events_outside_the_window(
    client, fake_email, fake_clock, tree
):
    headers = _student(client, fake_email)

    client.get("/content/topics/integers", headers=headers)
    client.post(
        "/mentisq/messages",
        json={"content": "old question"},
        headers=headers,
    )

    fake_clock.advance(timedelta(days=31))
    headers = _relogin(client)  # the original access token has long expired

    activity = client.get("/dashboard", headers=headers).json()["activity"]
    assert activity["topic_views"] == 0
    assert activity["topics_viewed"] == 0
    assert activity["mentisq_messages"] == 0


def test_failed_mentisq_turns_do_not_count_as_usage(
    client, fake_email, fake_llm, tree
):
    headers = _student(client, fake_email)
    fake_llm.mode = "error"

    resp = client.post(
        "/mentisq/messages",
        json={"content": "this one fails"},
        headers=headers,
    )
    assert resp.json()["status"] == "failed"

    activity = client.get("/dashboard", headers=headers).json()["activity"]
    assert activity["mentisq_messages"] == 0


# -- isolation --------------------------------------------------------------


def test_dashboard_is_scoped_to_the_caller(
    client, fake_email, tree
):
    ada = _student(client, fake_email)
    _submit(client, ada, tree["int_a"], "b")
    client.get("/content/topics/integers", headers=ada)

    bob = _other_student(
        client, fake_email, email="bob@example.com", name="Bob Bit"
    )
    body = client.get("/dashboard", headers=bob).json()
    assert body["recent_attempts"] == []
    assert body["topic_performance"] == []
    assert body["activity"]["topic_views"] == 0
