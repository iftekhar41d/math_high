"""Pure time arithmetic for the `timed` practice mode.

No DB, no clock, no request context — the router passes in the stored
`time_limit_seconds` / `started_at` and the current instant from the injected
`Clock`, and these functions turn them into the countdown, the late-answer flag,
and the final score. Kept separate from the router so the boundary maths is
unit-testable in isolation (in the mould of `grading.py`).
"""

from __future__ import annotations

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


def _elapsed_seconds(started_at: datetime, now: datetime) -> float:
    return (now - started_at).total_seconds()


def remaining_seconds(
    *, time_limit_seconds: int, started_at: datetime, now: datetime
) -> int:
    """Whole seconds left on the countdown, never negative. Zero once the
    limit has elapsed — that is what the SPA renders and auto-submits on.
    """
    left = time_limit_seconds - _elapsed_seconds(started_at, now)
    return max(0, int(left))


def is_after_limit(
    *, time_limit_seconds: int, started_at: datetime, now: datetime
) -> bool:
    """Whether `now` is past the quiz's limit — i.e. an answer submitted at
    this instant is a late one, stored with a flag rather than rejected.
    """
    return _elapsed_seconds(started_at, now) > time_limit_seconds


def score(correct_by_position: list[bool]) -> float:
    """Proportion correct over the frozen question set (0.0–1.0, rounded to
    four places). An unanswered question is passed in as `False`. An empty set
    scores 0.0.
    """
    if not correct_by_position:
        return 0.0
    return round(sum(correct_by_position) / len(correct_by_position), 4)
