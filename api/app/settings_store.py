"""Low-level get/put/delete over the `Setting` key/value table.

The typed accessors with in-code defaults live in the per-domain modules
(`app/analytics/settings.py`, `app/practice/settings.py`); this is only the
string-level storage underneath them. The caller commits.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Setting


def read_setting(db: Session, key: str) -> str | None:
    row = db.get(Setting, key)
    return row.value if row is not None else None


def write_setting(db: Session, key: str, value: str | None) -> None:
    """Upsert `key`; a `None` value deletes the row (restoring the default)."""
    row = db.get(Setting, key)
    if value is None:
        if row is not None:
            db.delete(row)
        return
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value
