"""Analytics recompute configuration, stored in the `Setting` key/value table.

Two keys, both with an in-code default so a fresh database needs no seeding:

- `analytics.mastery_half_life_days` — the exponential half-life (in days) used
  to recency-weight first-attempt outcomes. `SuperAdmin`-tunable; default ~14.
- `analytics.recompute_watermark` — an ISO-8601 UTC timestamp, the start of the
  last successful recompute. The next run only revisits students with a
  `QuestionAttempt` or `TopicView` strictly after it. Absent until the first
  run; not user-facing.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.settings_store import read_setting, write_setting

SETTING_MASTERY_HALF_LIFE_DAYS = "analytics.mastery_half_life_days"
SETTING_RECOMPUTE_WATERMARK = "analytics.recompute_watermark"

DEFAULT_MASTERY_HALF_LIFE_DAYS = 14.0


class AnalyticsSettings:
    """Typed reads/writes over the two `Setting` rows. The caller commits."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @property
    def mastery_half_life_days(self) -> float:
        raw = read_setting(self.db, SETTING_MASTERY_HALF_LIFE_DAYS)
        return DEFAULT_MASTERY_HALF_LIFE_DAYS if raw is None else float(raw)

    @property
    def watermark(self) -> datetime | None:
        raw = read_setting(self.db, SETTING_RECOMPUTE_WATERMARK)
        if raw is None:
            return None
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def set_watermark(self, when: datetime) -> None:
        write_setting(
            self.db,
            SETTING_RECOMPUTE_WATERMARK,
            when.astimezone(timezone.utc).isoformat(),
        )
