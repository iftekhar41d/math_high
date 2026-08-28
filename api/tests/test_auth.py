"""Auth flows, exercised end to end through the HTTP API.

Time comes from the fake `Clock`, outbound mail from the fake `EmailSender`;
nothing else is mocked. Tests assert on responses and persisted effects (a later
request succeeding or failing), not on internals.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from app.auth.config import (
    LOGIN_FAILURE_WINDOW,
    LOGIN_MAX_FAILURES,
    LOGIN_MAX_FAILURES_PER_IP,
    REFRESH_TOKEN_TTL,
)

REGISTER = {
    "email": "Ada@example.com",
    "password": "correct horse battery",
    "name": "Ada Lovelace",
    "year_level": 7,
}


def _token_from_last_email(fake_email) -> str:
    """Pull the `?token=` value out of the most recent email's link."""
    query = urlparse(_link(fake_email.last.body)).query
    return parse_qs(query)["token"][0]


def _link(body: str) -> str:
    for word in body.split():
        if word.startswith("http"):
            return word
    raise AssertionError(f"no link in email body: {body!r}")


def register(client, **overrides):
    return client.post("/auth/register", json={**REGISTER, **overrides})


def register_and_verify(client, fake_email, **overrides) -> dict:
    register(client, **overrides)
    token = _token_from_last_email(fake_email)
    assert client.post("/auth/verify-email", json={"token": token}).status_code == 200
    return {**REGISTER, **overrides}


def login(client, creds) -> "object":
    return client.post(
        "/auth/login", json={"email": creds["email"], "password": creds["password"]}
    )


@contextmanager
def presenting_refresh_cookie(client, value: str):
    """Temporarily force the refresh cookie to `value` (e.g. a superseded token)
    for the requests inside the block, then restore the jar."""
    saved = client.cookies.get("refresh_token")
    client.cookies.set("refresh_token", value)
    try:
        yield
    finally:
        client.cookies.delete("refresh_token")
        if saved is not None:
            client.cookies.set("refresh_token", saved)


# -- registration & verification ---------------------------------------------


def test_register_sends_a_verification_email(client, fake_email):
    resp = register(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "ada@example.com"  # normalised
    assert body["email_verified"] is False
    assert body["year_level"] == 7
    assert len(fake_email.sent) == 1
    assert fake_email.last.to == "ada@example.com"
    # The email carries a working token, nothing more.
    assert _token_from_last_email(fake_email)


def test_register_rejects_a_duplicate_email(client):
    assert register(client).status_code == 201
    dup = register(client, name="Someone Else")
    assert dup.status_code == 409


def test_password_is_hashed_not_stored_in_clear(client, db_session):
    register(client)
    from app.models import User

    user = db_session.query(User).one()
    assert user.password_hash is not None
    assert REGISTER["password"] not in user.password_hash
    assert user.password_hash.startswith("$2")  # bcrypt


def test_verification_link_marks_the_email_verified(client, fake_email):
    register(client)
    token = _token_from_last_email(fake_email)

    resp = client.post("/auth/verify-email", json={"token": token})
    assert resp.status_code == 200

    # And now login works.
    assert login(client, REGISTER).status_code == 200


def test_a_used_or_bogus_verification_token_is_rejected(client, fake_email):
    register(client)
    token = _token_from_last_email(fake_email)
    client.post("/auth/verify-email", json={"token": token})

    assert client.post("/auth/verify-email", json={"token": token}).status_code == 400
    assert client.post("/auth/verify-email", json={"token": "nope"}).status_code == 400


def test_unverified_login_is_refused_then_resend_sends_a_fresh_email(client, fake_email):
    register(client)
    first_token = _token_from_last_email(fake_email)

    refused = login(client, REGISTER)
    assert refused.status_code == 403
    assert "verify" in refused.json()["detail"].lower()

    resent = client.post("/auth/resend-verification", json={"email": REGISTER["email"]})
    assert resent.status_code == 200
    assert len(fake_email.sent) == 2
    fresh_token = _token_from_last_email(fake_email)
    assert fresh_token != first_token

    # The stale token is dead; the fresh one verifies.
    assert client.post(
        "/auth/verify-email", json={"token": first_token}
    ).status_code == 400
    assert client.post(
        "/auth/verify-email", json={"token": fresh_token}
    ).status_code == 200


def test_resend_is_quiet_for_unknown_or_already_verified_email(client, fake_email):
    # Unknown address: 200, no email.
    assert client.post(
        "/auth/resend-verification", json={"email": "ghost@example.com"}
    ).status_code == 200
    assert fake_email.sent == []

    register_and_verify(client, fake_email)
    before = len(fake_email.sent)
    assert client.post(
        "/auth/resend-verification", json={"email": REGISTER["email"]}
    ).status_code == 200
    assert len(fake_email.sent) == before  # nothing sent for a verified account


# -- login & session cookie ------------------------------------------------


def test_login_returns_access_token_and_sets_refresh_cookie(client, fake_email):
    register_and_verify(client, fake_email)

    resp = login(client, REGISTER)
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "ada@example.com"

    set_cookie = resp.headers["set-cookie"].lower()
    assert "refresh_token=" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert "refresh_token" in client.cookies


def test_refresh_cookie_is_marked_secure_when_not_disabled(
    client, fake_email, monkeypatch
):
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "1")
    register_and_verify(client, fake_email)
    resp = login(client, REGISTER)
    assert "secure" in resp.headers["set-cookie"].lower()


def test_wrong_password_is_401(client, fake_email):
    register_and_verify(client, fake_email)
    resp = client.post(
        "/auth/login", json={"email": REGISTER["email"], "password": "wrong"}
    )
    assert resp.status_code == 401


def test_access_token_reaches_a_protected_endpoint(client, fake_email):
    register_and_verify(client, fake_email)
    token = login(client, REGISTER).json()["access_token"]

    resp = client.get("/profile", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "ada@example.com"

    # No / malformed token → 401.
    assert client.get("/profile").status_code == 401
    assert client.get(
        "/profile", headers={"Authorization": "Bearer garbage"}
    ).status_code == 401


def test_access_token_expires_and_refresh_issues_a_new_one(client, fake_email, fake_clock):
    register_and_verify(client, fake_email)
    token = login(client, REGISTER).json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    assert client.get("/profile", headers=auth).status_code == 200

    fake_clock.advance(timedelta(minutes=16))
    assert client.get("/profile", headers=auth).status_code == 401

    # The refresh cookie is still good; it mints a fresh access token.
    refreshed = client.post("/auth/refresh")
    assert refreshed.status_code == 200
    new_token = refreshed.json()["access_token"]
    assert new_token != token
    assert client.get(
        "/profile", headers={"Authorization": f"Bearer {new_token}"}
    ).status_code == 200


# -- refresh rotation ----------------------------------------------------


def test_refresh_rotates_and_invalidates_the_previous_token(client, fake_email):
    register_and_verify(client, fake_email)
    login(client, REGISTER)
    old_refresh = client.cookies["refresh_token"]

    first = client.post("/auth/refresh")
    assert first.status_code == 200
    new_refresh = client.cookies["refresh_token"]
    assert new_refresh != old_refresh

    # Presenting the superseded cookie fails.
    with presenting_refresh_cookie(client, old_refresh):
        assert client.post("/auth/refresh").status_code == 401

    # The rotated-to cookie still works.
    assert client.post("/auth/refresh").status_code == 200


def test_refresh_without_a_cookie_is_401(client):
    assert client.post("/auth/refresh").status_code == 401


def test_refresh_token_is_rejected_once_its_lifetime_elapses(client, fake_email, fake_clock):
    register_and_verify(client, fake_email)
    login(client, REGISTER)

    fake_clock.advance(REFRESH_TOKEN_TTL + timedelta(days=1))
    assert client.post("/auth/refresh").status_code == 401


# -- logout / logout-all -------------------------------------------------


def test_logout_ends_the_current_session(client, fake_email):
    register_and_verify(client, fake_email)
    login(client, REGISTER)
    old_refresh = client.cookies["refresh_token"]

    assert client.post("/auth/logout").status_code == 200

    # Server-side revocation, not just a cleared cookie.
    with presenting_refresh_cookie(client, old_refresh):
        assert client.post("/auth/refresh").status_code == 401


def test_logout_all_bumps_generation_and_kills_every_refresh_token(client, fake_email):
    creds = register_and_verify(client, fake_email)

    login(client, creds)
    session_a = client.cookies["refresh_token"]
    access_a = login(client, creds).json()["access_token"]
    session_b = client.cookies["refresh_token"]
    assert session_a != session_b

    resp = client.post(
        "/auth/logout-all", headers={"Authorization": f"Bearer {access_a}"}
    )
    assert resp.status_code == 200

    for stale in (session_a, session_b):
        with presenting_refresh_cookie(client, stale):
            assert client.post("/auth/refresh").status_code == 401

    # Live access tokens from the old generation are rejected too.
    assert client.get(
        "/profile", headers={"Authorization": f"Bearer {access_a}"}
    ).status_code == 401

    # A fresh login still works.
    assert login(client, creds).status_code == 200


def test_logout_all_requires_authentication(client):
    assert client.post("/auth/logout-all").status_code == 401


# -- password recovery -------------------------------------------------


def test_forgot_then_reset_password_switches_the_valid_password(client, fake_email):
    creds = register_and_verify(client, fake_email)

    resp = client.post("/auth/forgot-password", json={"email": creds["email"]})
    assert resp.status_code == 200
    reset_token = _token_from_last_email(fake_email)

    new_password = "a brand new passphrase"
    done = client.post(
        "/auth/reset-password",
        json={"token": reset_token, "new_password": new_password},
    )
    assert done.status_code == 200

    # Old password is dead, new one works.
    assert login(client, creds).status_code == 401
    assert login(client, {**creds, "password": new_password}).status_code == 200


def test_reset_token_is_single_use_and_expires(client, fake_email, fake_clock):
    creds = register_and_verify(client, fake_email)
    client.post("/auth/forgot-password", json={"email": creds["email"]})
    token = _token_from_last_email(fake_email)

    assert client.post(
        "/auth/reset-password", json={"token": token, "new_password": "one two three four"}
    ).status_code == 200
    # Second use rejected.
    assert client.post(
        "/auth/reset-password", json={"token": token, "new_password": "five six seven eight"}
    ).status_code == 400

    # A brand new token, left to expire, is also rejected.
    client.post("/auth/forgot-password", json={"email": creds["email"]})
    stale = _token_from_last_email(fake_email)
    fake_clock.advance(timedelta(hours=2))
    assert client.post(
        "/auth/reset-password", json={"token": stale, "new_password": "nine ten eleven twelve"}
    ).status_code == 400


def test_forgot_password_is_quiet_for_an_unknown_email(client, fake_email):
    assert client.post(
        "/auth/forgot-password", json={"email": "nobody@example.com"}
    ).status_code == 200
    assert fake_email.sent == []


def test_reset_password_revokes_existing_sessions(client, fake_email):
    creds = register_and_verify(client, fake_email)
    login(client, creds)
    live_session = client.cookies["refresh_token"]

    client.post("/auth/forgot-password", json={"email": creds["email"]})
    token = _token_from_last_email(fake_email)
    client.post(
        "/auth/reset-password", json={"token": token, "new_password": "the new one here"}
    )

    with presenting_refresh_cookie(client, live_session):
        assert client.post("/auth/refresh").status_code == 401


# -- login rate limiting ------------------------------------------------


def test_lockout_after_repeated_failures_then_recovery_after_the_window(
    client, fake_email, fake_clock
):
    creds = register_and_verify(client, fake_email)
    bad = {"email": creds["email"], "password": "nope"}

    for _ in range(LOGIN_MAX_FAILURES):
        assert client.post("/auth/login", json=bad).status_code == 401

    # Further attempts are refused — even with the right password.
    assert client.post("/auth/login", json=bad).status_code == 429
    assert login(client, creds).status_code == 429

    # Advancing past the window clears the lockout.
    fake_clock.advance(LOGIN_FAILURE_WINDOW + timedelta(minutes=1))
    assert login(client, creds).status_code == 200


def test_lockout_is_scoped_to_one_email(client, fake_email, fake_clock):
    creds = register_and_verify(client, fake_email)
    other = register_and_verify(
        client, fake_email, email="grace@example.com", name="Grace Hopper"
    )

    for _ in range(LOGIN_MAX_FAILURES):
        client.post(
            "/auth/login", json={"email": creds["email"], "password": "nope"}
        )
    assert login(client, creds).status_code == 429
    # A different account on the same host is unaffected (well under the IP cap).
    assert login(client, other).status_code == 200


def test_a_successful_login_clears_the_failure_window(client, fake_email):
    creds = register_and_verify(client, fake_email)
    bad = {"email": creds["email"], "password": "nope"}

    for _ in range(LOGIN_MAX_FAILURES - 1):
        assert client.post("/auth/login", json=bad).status_code == 401

    # A correct login resets the count...
    assert login(client, creds).status_code == 200

    # ...so the next four misses don't trip the lockout.
    for _ in range(LOGIN_MAX_FAILURES - 1):
        assert client.post("/auth/login", json=bad).status_code == 401
    assert login(client, creds).status_code == 200


def test_one_host_hammering_many_emails_is_locked_out_by_ip(client, fake_email):
    # No account needed — every attempt is a miss, but they share an IP.
    for i in range(LOGIN_MAX_FAILURES_PER_IP):
        client.post("/auth/login", json={"email": f"u{i}@example.com", "password": "x"})

    # A brand new email from the same host is now refused.
    resp = client.post("/auth/login", json={"email": "fresh@example.com", "password": "x"})
    assert resp.status_code == 429
