"""Auth tunables. Durations are the spec's ballpark values; the two cookie
switches are env-driven so tests (HTTP, no TLS) and prod (HTTPS) both work.
"""

from __future__ import annotations

import os
from datetime import timedelta

ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=30)
EMAIL_VERIFICATION_TTL = timedelta(hours=24)
PASSWORD_RESET_TTL = timedelta(hours=1)

# Login rate limiting. Inside the window, this many failed attempts for one
# email — or the looser per-IP count, which guards a single host hammering many
# addresses without locking out a whole household after five typos — refuses
# further attempts until the failures age out (or, for the email, until a
# success resets the window).
LOGIN_FAILURE_WINDOW = timedelta(minutes=15)
LOGIN_MAX_FAILURES = 5
LOGIN_MAX_FAILURES_PER_IP = 20

REFRESH_COOKIE_NAME = "refresh_token"

# HS256 secret for access tokens. A real secret is set via env on the VPS; the
# dev default is fine locally because access tokens are short-lived and the
# refresh cookie is the thing that actually persists a session.
JWT_ALGORITHM = "HS256"


def jwt_secret() -> str:
    return os.getenv("JWT_SECRET", "dev-insecure-secret-change-me")


def cookie_secure() -> bool:
    """`Secure` on the refresh cookie. Off only when explicitly disabled (tests
    run over plain HTTP; httpx would silently drop a Secure cookie)."""
    return os.getenv("AUTH_COOKIE_SECURE", "1") != "0"


def public_base_url() -> str:
    """Origin used to build verification / reset links in emails. Defaults to
    the live host; set `PUBLIC_BASE_URL=http://localhost:5173` for local dev."""
    return os.getenv("PUBLIC_BASE_URL", "https://math.mentisq.com").rstrip("/")
