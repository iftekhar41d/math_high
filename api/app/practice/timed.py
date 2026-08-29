"""Pure time arithmetic for the `timed` practice mode.

No DB, no clock, no request context — the router builds a `Countdown` from the
stored `time_limit_seconds` / `started_at` and asks it the time-relative
questions against an instant from the injected `Clock`. Kept separate from the
router so the boundary maths is unit-testable in isolation (in the mould of
`grading.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


def total_time_limit(
    estimated_seconds: list[int | None], default_seconds: int
) -> int:
    """The quiz's overall limit: the sum of each question's
    `estimated_time_seconds`, with `default_seconds` standing in wherever a
    question carries none. An empty question set yields 0.
    """
    return sum(
        s if s is not None else default_seconds for s in estimated_seconds
    )


@dataclass(frozen=True)
class Countdown:
    """A timed quiz's clock: how long it runs for and when it started. Every
    time-relative question the router asks — seconds left, is an answer late —
    is answered here from a `now` the caller passes in, so the arithmetic stays
    pure.
    """

    time_limit_seconds: int
    started_at: datetime

    def _elapsed(self, now: datetime) -> float:
        return (now - self.started_at).total_seconds()

    def remaining(self, now: datetime) -> int:
        """Whole seconds left, never negative. Zero once the limit has
        elapsed — what the SPA renders and auto-submits on."""
        return max(0, int(self.time_limit_seconds - self._elapsed(now)))

    def is_after_limit(self, now: datetime) -> bool:
        """Whether `now` is past the limit — an answer at this instant is a
        late one, stored with a flag rather than rejected."""
        return self._elapsed(now) > self.time_limit_seconds


def proportion_correct(correct_by_position: list[bool]) -> float:
    """Proportion correct over the frozen question set (0.0–1.0, rounded to
    four places). An unanswered question is passed in as `False`. An empty set
    scores 0.0.
    """
    if not correct_by_position:
        return 0.0
    return round(sum(correct_by_position) / len(correct_by_position), 4)
