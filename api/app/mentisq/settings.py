"""MentisQ configuration.

Two sources, on purpose:

- **The OpenRouter model name comes only from the environment**
  (`OPENROUTER_MODEL`), alongside the API key (`OPENROUTER_API_KEY`, read in
  `llm_client.py`). Neither is ever stored in the database. Change the model by
  editing the env file and restarting the service.
- **The usage caps are `SuperAdmin`-editable at runtime** and live in the
  `Setting` key/value table: `daily_message_cap`,
  `per_student_monthly_cap_usd`, and the nullable `global_monthly_cap_usd`
  (default `None` = no global ceiling; clearing the row restores that). Each has
  an in-code default below; a `Setting` row only ever overrides one.
"""

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from app.models import Setting

SETTING_DAILY_MESSAGE_CAP = "mentisq.daily_message_cap"
SETTING_PER_STUDENT_MONTHLY_CAP_USD = "mentisq.per_student_monthly_cap_usd"
SETTING_GLOBAL_MONTHLY_CAP_USD = "mentisq.global_monthly_cap_usd"

# Env var carrying the OpenRouter model id (e.g. "openai/gpt-4o-mini").
MODEL_NAME_ENV_VAR = "OPENROUTER_MODEL"
DEFAULT_MODEL_NAME = "openai/gpt-4o-mini"

# A runaway-loop backstop, not a product limit — multi-turn sessions make a low
# per-day ceiling too easy to hit in normal use. The monthly USD cap
# (`per_student_monthly_cap_usd`) is the real spend guard.
DEFAULT_DAILY_MESSAGE_CAP = 2000
DEFAULT_PER_STUDENT_MONTHLY_CAP_USD = 50.0
DEFAULT_GLOBAL_MONTHLY_CAP_USD: float | None = None

_UNSET = object()


def model_name() -> str:
    """The OpenRouter model id, from `OPENROUTER_MODEL` (falling back to a sane
    default so local dev and tests work without it set)."""
    return os.getenv(MODEL_NAME_ENV_VAR) or DEFAULT_MODEL_NAME


class MentisQSettings:
    """The runtime-editable caps. Reads/writes `Setting` rows; the caller
    commits. `model_name` is exposed read-only for display — it is not stored
    here and cannot be updated through this class."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # -- raw row access -------------------------------------------------------

    def _raw(self, key: str) -> str | None:
        row = self.db.get(Setting, key)
        return row.value if row is not None else None

    def _write(self, key: str, value: str | None) -> None:
        row = self.db.get(Setting, key)
        if value is None:
            if row is not None:
                self.db.delete(row)
            return
        if row is None:
            self.db.add(Setting(key=key, value=value))
        else:
            row.value = value

    # -- typed reads -------------------------------------------------------

    @property
    def model_name(self) -> str:
        return model_name()

    @property
    def daily_message_cap(self) -> int:
        raw = self._raw(SETTING_DAILY_MESSAGE_CAP)
        return DEFAULT_DAILY_MESSAGE_CAP if raw is None else int(raw)

    @property
    def per_student_monthly_cap_usd(self) -> float:
        raw = self._raw(SETTING_PER_STUDENT_MONTHLY_CAP_USD)
        return (
            DEFAULT_PER_STUDENT_MONTHLY_CAP_USD if raw is None else float(raw)
        )

    @property
    def global_monthly_cap_usd(self) -> float | None:
        raw = self._raw(SETTING_GLOBAL_MONTHLY_CAP_USD)
        return DEFAULT_GLOBAL_MONTHLY_CAP_USD if raw is None else float(raw)

    def as_dict(self) -> dict:
        return {
            "model_name": self.model_name,
            "daily_message_cap": self.daily_message_cap,
            "per_student_monthly_cap_usd": self.per_student_monthly_cap_usd,
            "global_monthly_cap_usd": self.global_monthly_cap_usd,
        }

    # -- typed writes -------------------------------------------------------

    def update(
        self,
        *,
        daily_message_cap=_UNSET,
        per_student_monthly_cap_usd=_UNSET,
        global_monthly_cap_usd=_UNSET,
    ) -> None:
        """Persist only the fields actually passed. `global_monthly_cap_usd`
        accepts `None` explicitly — it clears the override. The caller commits.
        """
        if daily_message_cap is not _UNSET:
            self._write(
                SETTING_DAILY_MESSAGE_CAP, str(int(daily_message_cap))
            )
        if per_student_monthly_cap_usd is not _UNSET:
            self._write(
                SETTING_PER_STUDENT_MONTHLY_CAP_USD,
                repr(float(per_student_monthly_cap_usd)),
            )
        if global_monthly_cap_usd is not _UNSET:
            self._write(
                SETTING_GLOBAL_MONTHLY_CAP_USD,
                None
                if global_monthly_cap_usd is None
                else repr(float(global_monthly_cap_usd)),
            )
