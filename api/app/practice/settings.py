"""Practice tunables stored in the `Setting` key/value table.

`solution_reveal_after_attempts` — how many graded submissions a student must
make on a Question before `POST /practice/questions/{id}/submit` returns its
worked solution in the response. The default of 1 preserves the original
behaviour: the worked solution comes back from the first submission on. The
explicit `POST .../show-solution` escape hatch is unaffected — asking for the
solution outright always returns it.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.settings_store import read_setting

SETTING_SOLUTION_REVEAL_AFTER_ATTEMPTS = "practice.solution_reveal_after_attempts"
DEFAULT_SOLUTION_REVEAL_AFTER_ATTEMPTS = 1


def solution_reveal_after_attempts(db: Session) -> int:
    raw = read_setting(db, SETTING_SOLUTION_REVEAL_AFTER_ATTEMPTS)
    if raw is None:
        return DEFAULT_SOLUTION_REVEAL_AFTER_ATTEMPTS
    return int(raw)
