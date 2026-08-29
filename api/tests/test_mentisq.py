"""MentisQ guided exchange, usage caps, and the SuperAdmin settings endpoint,
exercised through the HTTP API.

The provider is the canned `FakeMentisQLLMClient` (flip `.mode` to force the
failure paths); time is the advanceable `FakeClock`. Tests assert on responses
and on the persisted `MentisQSession` / `MentisQMessage` rows — never internals.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.mentisq.service import (
    FALLBACK_MESSAGE,
    LIMIT_REACHED_DAILY,
    LIMIT_REACHED_MONTHLY,
)
from app.models import (
    CONTENT_DRAFT,
    CONTENT_PUBLISHED,
    ROLE_SUPER_ADMIN,
    LectureContent,
    MentisQMessage,
    MentisQSession,
    Question,
    Subject,
    Topic,
    Unit,
    User,
    YearLevel,
)
from tests.test_auth import login, register_and_verify
from tests.test_content import _student


@pytest.fixture
def mentisq_tree(db_session):
    """Year 7 → Mathematics → Number → "Integers" (published) with one question,
    plus a draft-only Topic."""
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

    q = Question(
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
        worked_solution="Start at -3, count up 5 to reach 2.",
    )
    db_session.add(q)
    db_session.commit()
    return {"question_id": q.id}


def _super_admin(client, fake_email, db_session):
    creds = register_and_verify(
        client, fake_email, email="root@example.com", name="Root Admin"
    )
    user = db_session.query(User).filter_by(email="root@example.com").one()
    user.role = ROLE_SUPER_ADMIN
    db_session.commit()
    token = login(client, creds).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _ask(client, headers, content="I'm stuck on this", **ctx):
    return client.post(
        "/mentisq/messages", json={"content": content, **ctx}, headers=headers
    )


def _set_settings(client, admin_headers, **fields):
    resp = client.put(
        "/admin/mentisq-settings", json=fields, headers=admin_headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# -- a successful guided exchange -----------------------------------------


def test_guided_exchange_persists_both_turns_with_usage(
    client, fake_email, fake_llm, db_session, mentisq_tree
):
    headers = _student(client, fake_email)
    resp = _ask(client, headers, content="How do I start?")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["reply"] == "What have you tried so far?"

    session = db_session.get(MentisQSession, body["session_id"])
    assert session.mode == "guided"
    assert session.context_topic_id is None
    assert session.context_question_id is None

    msgs = (
        db_session.query(MentisQMessage)
        .filter_by(session_id=session.id)
        .order_by(MentisQMessage.id)
        .all()
    )
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert [m.status for m in msgs] == ["ok", "ok"]
    user_turn, assistant_turn = msgs
    assert user_turn.content == "How do I start?"
    assert assistant_turn.content == "What have you tried so far?"
    # Provider usage is split across the pair: prompt tokens on the student's
    # turn, completion tokens + USD cost on the tutor's.
    assert user_turn.prompt_tokens == 120
    assert user_turn.completion_tokens == 0
    assert user_turn.cost_usd == 0.0
    assert assistant_turn.prompt_tokens == 0
    assert assistant_turn.completion_tokens == 18
    assert assistant_turn.cost_usd == pytest.approx(0.0012)
    assert len(fake_llm.calls) == 1
    assert fake_llm.calls[0]["model"] == "openai/gpt-4o-mini"


def test_question_context_is_injected_but_never_returned_verbatim(
    client, fake_email, fake_llm, db_session, mentisq_tree
):
    headers = _student(client, fake_email)
    resp = _ask(
        client, headers, content="Is it 8?", question_id=mentisq_tree["question_id"]
    )
    assert resp.status_code == 200
    raw = resp.text

    # The prompt the provider saw carries the correct answer + worked solution…
    prompt = fake_llm.calls[0]["prompt"]
    assert "count up 5 to reach 2" in prompt
    assert "b) 2" in prompt
    # …but none of that leaks back to the student.
    assert "count up 5 to reach 2" not in raw
    assert "correct_option" not in raw

    session = db_session.get(MentisQSession, resp.json()["session_id"])
    assert session.context_question_id == mentisq_tree["question_id"]


def test_topic_context_injects_the_lecture_body_and_records_the_topic(
    client, fake_email, fake_llm, db_session, mentisq_tree
):
    headers = _student(client, fake_email)
    ok = _ask(client, headers, topic_slug="integers")
    assert ok.status_code == 200
    session = db_session.get(MentisQSession, ok.json()["session_id"])
    assert session.context_topic_id is not None
    # The lecture body ("# Integers") is handed to the tutor as context.
    assert "# Integers" in fake_llm.calls[0]["prompt"]


def test_draft_or_unknown_topic_context_is_404(client, fake_email, mentisq_tree):
    headers = _student(client, fake_email)
    assert _ask(client, headers, topic_slug="draft-topic").status_code == 404
    assert _ask(client, headers, topic_slug="nope").status_code == 404


def test_topic_and_question_context_together_is_rejected(
    client, fake_email, mentisq_tree
):
    headers = _student(client, fake_email)
    resp = _ask(
        client,
        headers,
        topic_slug="integers",
        question_id=mentisq_tree["question_id"],
    )
    assert resp.status_code == 422


# -- provider failure paths ---------------------------------------------


@pytest.mark.parametrize("mode", ["timeout", "error"])
def test_provider_failure_returns_fallback_and_stores_failed_unmetered(
    client, fake_email, fake_llm, db_session, mentisq_tree, mode
):
    headers = _student(client, fake_email)
    fake_llm.mode = mode

    resp = _ask(client, headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["reply"] == FALLBACK_MESSAGE

    msgs = (
        db_session.query(MentisQMessage)
        .filter_by(session_id=body["session_id"])
        .order_by(MentisQMessage.id)
        .all()
    )
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert [m.status for m in msgs] == ["failed", "failed"]
    assert msgs[1].content == FALLBACK_MESSAGE
    assert msgs[1].cost_usd == 0.0
    assert len(fake_llm.calls) == 1


# -- usage caps -------------------------------------------------------------


def test_daily_message_cap_blocks_the_next_message_without_an_llm_call(
    client, fake_email, fake_llm, db_session, mentisq_tree
):
    admin = _super_admin(client, fake_email, db_session)
    _set_settings(client, admin, daily_message_cap=1)
    student = _student(client, fake_email)

    first = _ask(client, student)
    assert first.json()["status"] == "ok"
    assert len(fake_llm.calls) == 1

    second = _ask(client, student)
    assert second.status_code == 200
    assert second.json()["status"] == "limit_reached"
    assert second.json()["reply"] == LIMIT_REACHED_DAILY
    assert second.json()["session_id"] is None
    # No provider call, and no session row, for the blocked message.
    assert len(fake_llm.calls) == 1
    assert db_session.query(MentisQSession).count() == 1


def test_daily_cap_window_resets_the_next_day(
    client, fake_email, fake_clock, fake_llm, db_session, mentisq_tree
):
    admin = _super_admin(client, fake_email, db_session)
    _set_settings(client, admin, daily_message_cap=1)
    creds = register_and_verify(client, fake_email)
    student = {
        "Authorization": f"Bearer {login(client, creds).json()['access_token']}"
    }

    assert _ask(client, student).json()["status"] == "ok"
    assert _ask(client, student).json()["status"] == "limit_reached"

    fake_clock.advance(timedelta(days=1))
    # A fresh access token for the advanced clock (the old one has expired).
    student = {
        "Authorization": f"Bearer {login(client, creds).json()['access_token']}"
    }
    assert _ask(client, student).json()["status"] == "ok"
    assert len(fake_llm.calls) == 2


def test_monthly_spend_cap_blocks_the_next_message_without_an_llm_call(
    client, fake_email, fake_llm, db_session, mentisq_tree
):
    admin = _super_admin(client, fake_email, db_session)
    # The fake exchange costs $0.0012; a $0.001 ceiling clears once, then bites.
    _set_settings(client, admin, per_student_monthly_cap_usd=0.001)
    student = _student(client, fake_email)

    first = _ask(client, student)
    assert first.json()["status"] == "ok"

    second = _ask(client, student)
    assert second.json()["status"] == "limit_reached"
    assert second.json()["reply"] == LIMIT_REACHED_MONTHLY
    assert len(fake_llm.calls) == 1


def test_global_monthly_cap_blocks_across_students(
    client, fake_email, fake_llm, db_session, mentisq_tree
):
    admin = _super_admin(client, fake_email, db_session)
    _set_settings(client, admin, global_monthly_cap_usd=0.001)
    student = _student(client, fake_email)

    assert _ask(client, student).json()["status"] == "ok"

    other_creds = register_and_verify(
        client, fake_email, email="other@example.com", name="Other Student"
    )
    other = {
        "Authorization": f"Bearer {login(client, other_creds).json()['access_token']}"
    }
    blocked = _ask(client, other)
    assert blocked.json()["status"] == "limit_reached"
    assert len(fake_llm.calls) == 1


def test_a_failed_turn_does_not_consume_the_daily_allowance(
    client, fake_email, fake_llm, db_session, mentisq_tree
):
    admin = _super_admin(client, fake_email, db_session)
    _set_settings(client, admin, daily_message_cap=2)
    student = _student(client, fake_email)

    assert _ask(client, student).json()["status"] == "ok"  # 1 of 2

    fake_llm.mode = "timeout"
    assert _ask(client, student).json()["status"] == "failed"  # unmetered

    fake_llm.mode = "ok"
    # Still allowed — the failed turn didn't count as the 2nd message.
    assert _ask(client, student).json()["status"] == "ok"  # 2 of 2
    # And now the cap does bite.
    assert _ask(client, student).json()["status"] == "limit_reached"


def test_lowering_a_cap_via_the_settings_api_blocks_the_next_message(
    client, fake_email, fake_llm, db_session, mentisq_tree
):
    admin = _super_admin(client, fake_email, db_session)
    student = _student(client, fake_email)

    assert _ask(client, student).json()["status"] == "ok"
    assert _ask(client, student).json()["status"] == "ok"
    calls_before = len(fake_llm.calls)

    _set_settings(client, admin, daily_message_cap=2)

    blocked = _ask(client, student)
    assert blocked.json()["status"] == "limit_reached"
    assert len(fake_llm.calls) == calls_before


# -- SuperAdmin settings endpoint --------------------------------------


def test_settings_get_returns_defaults_then_reflects_updates(
    client, fake_email, db_session
):
    admin = _super_admin(client, fake_email, db_session)

    got = client.get("/admin/mentisq-settings", headers=admin).json()
    assert got == {
        "model_name": "openai/gpt-4o-mini",
        "daily_message_cap": 30,
        "per_student_monthly_cap_usd": 50.0,
        "global_monthly_cap_usd": None,
    }

    _set_settings(
        client,
        admin,
        model_name="anthropic/claude-3.5-haiku",
        daily_message_cap=10,
        global_monthly_cap_usd=25.5,
    )
    got = client.get("/admin/mentisq-settings", headers=admin).json()
    assert got["model_name"] == "anthropic/claude-3.5-haiku"
    assert got["daily_message_cap"] == 10
    assert got["per_student_monthly_cap_usd"] == 50.0  # untouched
    assert got["global_monthly_cap_usd"] == 25.5

    # An explicit null clears the global ceiling again.
    _set_settings(client, admin, global_monthly_cap_usd=None)
    got = client.get("/admin/mentisq-settings", headers=admin).json()
    assert got["global_monthly_cap_usd"] is None


def test_settings_endpoint_refuses_non_super_admin(
    client, fake_email, db_session, mentisq_tree
):
    student = _student(client, fake_email)
    assert client.get("/admin/mentisq-settings", headers=student).status_code == 403
    assert (
        client.put(
            "/admin/mentisq-settings",
            json={"daily_message_cap": 1},
            headers=student,
        ).status_code
        == 403
    )
    assert client.get("/admin/mentisq-settings").status_code == 401


def test_mentisq_endpoint_requires_authentication(client, mentisq_tree):
    assert client.post("/mentisq/messages", json={"content": "hi"}).status_code == 401


def test_model_name_setting_is_used_for_the_provider_call(
    client, fake_email, fake_llm, db_session, mentisq_tree
):
    admin = _super_admin(client, fake_email, db_session)
    _set_settings(client, admin, model_name="test/model-x")
    student = _student(client, fake_email)

    _ask(client, student)
    assert fake_llm.calls[-1]["model"] == "test/model-x"
