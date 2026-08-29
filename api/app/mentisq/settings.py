"""Typed accessors over the `Setting` key/value table for the `SuperAdmin`-
managed MentisQ configuration: the model name and the usage caps.

Every value has an in-code default here; a `Setting` row only ever overrides
one. `global_monthly_cap_usd` is genuinely optional — its default is `None`
(no global ceiling) and clearing the row restores that.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Setting

SETTING_MODEL_NAME = "mentisq.model_name"
SETTING_DAILY_MESSAGE_CAP = "mentisq.daily_message_cap"
SETTING_PER_STUDENT_MONTHLY_CAP_USD = "mentisq.per_student_monthly_cap_usd"
SETTING_GLOBAL_MONTHLY_CAP_USD = "mentisq.global_monthly_cap_usd"

DEFAULT_MODEL_NAME = "openai/gpt-4o-mini"
DEFAULT_DAILY_MESSAGE_CAP = 30
DEFAULT_PER_STUDENT_MONTHLY_CAP_USD = 50.0
DEFAULT_GLOBAL_MONTHLY_CAP_USD: float | None = None

_UNSET = object()


class MentisQSettings:
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
        return self._raw(SETTING_MODEL_NAME) or DEFAULT_MODEL_NAME

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
        model_name=_UNSET,
        daily_message_cap=_UNSET,
        per_student_monthly_cap_usd=_UNSET,
        global_monthly_cap_usd=_UNSET,
    ) -> None:
        """Persist only the fields actually passed. `global_monthly_cap_usd`
        accepts `None` explicitly — it clears the override. The caller commits.
        """
        if model_name is not _UNSET:
            self._write(SETTING_MODEL_NAME, str(model_name))
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
