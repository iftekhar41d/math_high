"""The `Clock` boundary — the only source of "now" in the app.

Every time-dependent decision (token expiry, refresh rotation, login-lockout
windows, the MentisQ daily message cap, the monthly spend window) reads the
current time through an injected `Clock` so tests can make time deterministic
with a fake instead of `sleep`.
"""

from datetime import datetime, timezone


class Clock:
    """Real wall-clock time, always timezone-aware UTC."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


def get_clock() -> Clock:
    """FastAPI dependency. Overridden with an advanceable fake in tests."""
    return Clock()
