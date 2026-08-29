"""Analytics recompute: cached mastery figures from stored attempt history.

The reusable core a future scheduler or admin trigger calls directly; the CLI
(`python -m app.analytics.recompute`) is only a wrapper.

* `app.analytics.recompute.recompute(db, clock, *, full=False)` — rebuild
  `PerformanceSnapshot` rows, incrementally by default. Imported from the
  submodule (not re-exported here) so `python -m app.analytics.recompute` does
  not double-import.
* `AnalyticsSettings` — typed access to the half-life and watermark `Setting`s.
* `FirstAttempt`, `time_weighted_mastery`, `trend` — the pure mastery maths.
"""

from app.analytics.mastery import FirstAttempt, time_weighted_mastery, trend
from app.analytics.settings import AnalyticsSettings

__all__ = [
    "AnalyticsSettings",
    "FirstAttempt",
    "time_weighted_mastery",
    "trend",
]
