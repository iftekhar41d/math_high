"""The boundary fakes are the seam every later ticket builds its tests on, so
their contract is pinned here.
"""

from datetime import timedelta

import pytest
from sqlalchemy import text

from app.email_sender import EmailMessage
from app.mentisq.llm_client import LLMError, LLMTimeoutError


def test_fake_email_records_sent_messages(fake_email):
    fake_email.send(EmailMessage(to="s@example.com", subject="Verify", body="link: abc"))
    assert len(fake_email.sent) == 1
    assert fake_email.last.to == "s@example.com"
    assert "abc" in fake_email.last.body


def test_fake_llm_returns_canned_completion_with_usage(fake_llm):
    messages = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "help me"},
    ]
    result = fake_llm.complete(messages=messages, model="test/model")

    assert result.text == "What have you tried so far?"
    assert result.prompt_tokens == 120
    assert result.completion_tokens == 18
    assert result.cost_usd == pytest.approx(0.0012)
    assert fake_llm.calls[0]["messages"] == messages
    assert fake_llm.calls[0]["model"] == "test/model"
    # The flattened `prompt` view carries every message's text.
    assert fake_llm.calls[0]["prompt"] == "rules\nhelp me"


def test_fake_llm_can_be_switched_to_timeout(fake_llm):
    fake_llm.mode = "timeout"
    with pytest.raises(LLMTimeoutError):
        fake_llm.complete(messages=[{"role": "user", "content": "x"}], model="m")


def test_fake_llm_can_be_switched_to_error(fake_llm):
    fake_llm.mode = "error"
    with pytest.raises(LLMError):
        fake_llm.complete(messages=[{"role": "user", "content": "x"}], model="m")


def test_fake_clock_is_advanceable(fake_clock):
    start = fake_clock.now()
    fake_clock.advance(timedelta(minutes=15))
    assert fake_clock.now() - start == timedelta(minutes=15)


def test_each_test_gets_a_fresh_database(client, db_session):
    # No tables/rows leak in from other tests: the schema is empty in the
    # skeleton and the engine is per-test. This just asserts the wiring holds.
    assert db_session.execute(text("SELECT 1")).scalar() == 1
