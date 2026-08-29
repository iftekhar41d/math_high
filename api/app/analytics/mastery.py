"""Pure mastery / trend maths — no database, no clock, no I/O.

The recompute orchestrator (`recompute.py`) turns a student's attempt history
into a list of `FirstAttempt` per dimension and hands it here.

Definitions (see ticket 01):

- **mastery** — exponentially time-weighted proportion correct over the first
  graded attempt of each Question. A first attempt `d` days old carries weight
  ``0.5 ** (d / half_life)``; mastery is ``sum(weight * correct) / sum(weight)``.
- **trend** — the bucketed sign of (mastery over the last 30 days) minus
  (mastery over the prior 30 days), each computed with the same time-weighting
  as the headline figure. A gap of ``TREND_DEAD_ZONE`` or less reads as
  ``flat``; either window empty also reads ``flat`` (not enough to call a
  direction).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.models import TREND_DOWN, TREND_FLAT, TREND_UP

# A window-to-window mastery gap this small (5 points) is noise, not a trend.
TREND_DEAD_ZONE = 0.05
# Each trend window is this many days wide.
TREND_WINDOW_DAYS = 30


@dataclass(frozen=True)
class FirstAttempt:
    """One Question's first-attempt outcome, as it feeds a snapshot."""

    correct: bool
    at: datetime


def _age_days(at: datetime, now: datetime) -> float:
    return max((now - at).total_seconds(), 0.0) / 86400.0


def time_weighted_mastery(
    attempts: list[FirstAttempt],
    *,
    now: datetime,
    half_life_days: float,
) -> float:
    """Recency-weighted proportion correct. `attempts` must be non-empty."""
    total_weight = 0.0
    correct_weight = 0.0
    for a in attempts:
        weight = 0.5 ** (_age_days(a.at, now) / half_life_days)
        total_weight += weight
        if a.correct:
            correct_weight += weight
    # `_age_days` floors at 0 and half_life_days > 0, so every weight is in
    # (0, 1] and a non-empty list cannot sum to zero.
    return correct_weight / total_weight


def _window_mastery(
    attempts: list[FirstAttempt], *, now: datetime, half_life_days: float
) -> float | None:
    if not attempts:
        return None
    return time_weighted_mastery(
        attempts, now=now, half_life_days=half_life_days
    )


def trend(
    attempts: list[FirstAttempt],
    *,
    now: datetime,
    half_life_days: float,
) -> str:
    """`up` / `flat` / `down` from the two most recent 30-day windows."""
    recent_start = now - timedelta(days=TREND_WINDOW_DAYS)
    prior_start = now - timedelta(days=2 * TREND_WINDOW_DAYS)

    recent = [a for a in attempts if recent_start <= a.at <= now]
    prior = [a for a in attempts if prior_start <= a.at < recent_start]

    recent_m = _window_mastery(recent, now=now, half_life_days=half_life_days)
    prior_m = _window_mastery(prior, now=now, half_life_days=half_life_days)
    if recent_m is None or prior_m is None:
        return TREND_FLAT

    delta = recent_m - prior_m
    if delta > TREND_DEAD_ZONE:
        return TREND_UP
    if delta < -TREND_DEAD_ZONE:
        return TREND_DOWN
    return TREND_FLAT
