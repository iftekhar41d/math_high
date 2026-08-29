"""In-memory fakes for the three external-boundary adapters.

Wired in via FastAPI dependency overrides in `conftest.py`. Nothing else in the
stack is faked — routers, services, grading, and the DB are all real.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.clock import Clock
from app.email_sender import EmailMessage, EmailSender
from app.mentisq.llm_client import (
    LLMCompletion,
    LLMError,
    LLMTimeoutError,
    MentisQLLMClient,
)

# A fixed, timezone-aware instant tests start from unless they pass their own.
DEFAULT_START = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


class FakeClock(Clock):
    """Advanceable clock — no `sleep` needed for expiry / lockout / cap windows."""

    def __init__(self, start: datetime = DEFAULT_START) -> None:
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta

    def set(self, when: datetime) -> None:
        self._now = when


class FakeEmailSender(EmailSender):
    """Records every message so tests can pull verification / reset tokens out."""

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.sent.append(message)

    @property
    def last(self) -> EmailMessage:
        return self.sent[-1]


class FakeMentisQLLMClient(MentisQLLMClient):
    """Canned completion + usage. Switch `mode` to exercise the failure paths."""

    def __init__(self) -> None:
        self.mode: str = "ok"  # "ok" | "timeout" | "error"
        self.completion = LLMCompletion(
            text="What have you tried so far?",
            prompt_tokens=120,
            completion_tokens=18,
            cost_usd=0.0012,
        )
        self.calls: list[dict] = []

    def complete(
        self, *, messages: list[dict[str, str]], model: str
    ) -> LLMCompletion:
        # `messages` is the full OpenAI-style list (system + history + new user
        # turn). `prompt` is a flattened join kept for assertions that only care
        # that some text reached the provider.
        self.calls.append(
            {
                "messages": messages,
                "prompt": "\n".join(m["content"] for m in messages),
                "model": model,
            }
        )
        if self.mode == "timeout":
            raise LLMTimeoutError("fake timeout")
        if self.mode == "error":
            raise LLMError("fake provider error")
        return self.completion
