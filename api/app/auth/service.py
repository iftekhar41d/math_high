"""The reusable auth core. The HTTP routers are thin wrappers over this.

Every method takes its time from the `Clock` handed to the constructor. Nothing
here touches cookies, request objects, or `HTTPException` — those belong to the
router. Failure modes are raised as the small exception hierarchy below so the
router can map each to a status code.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.config import (
    EMAIL_VERIFICATION_TTL,
    LOGIN_FAILURE_WINDOW,
    LOGIN_MAX_FAILURES,
    LOGIN_MAX_FAILURES_PER_IP,
    PASSWORD_RESET_TTL,
    REFRESH_TOKEN_TTL,
)
from app.auth.jwt import create_access_token
from app.auth.passwords import hash_password, verify_password
from app.clock import Clock
from app.models import (
    EmailVerificationToken,
    LoginAttempt,
    PasswordResetToken,
    RefreshToken,
    User,
)


class AuthError(Exception):
    """Base for every expected auth failure."""


class EmailAlreadyRegistered(AuthError):
    pass


class InvalidToken(AuthError):
    """A verification / reset / refresh token is unknown, spent, or expired."""


class InvalidCredentials(AuthError):
    pass


class EmailNotVerified(AuthError):
    pass


class AccountLocked(AuthError):
    pass


@dataclass(frozen=True)
class IssuedSession:
    access_token: str
    refresh_token: str


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _is_unusable(row, now: datetime) -> bool:
    """True if a single-use token row is missing, already spent, or expired."""
    return row is None or row.used_at is not None or row.expires_at < now


class AuthService:
    def __init__(self, db: Session, clock: Clock) -> None:
        self.db = db
        self.clock = clock

    # -- registration & verification -------------------------------------

    def register(
        self, *, email: str, password: str, name: str, year_level: int
    ) -> tuple[User, str]:
        email = email.strip().lower()
        exists = self.db.scalar(select(User).where(User.email == email))
        if exists is not None:
            raise EmailAlreadyRegistered(email)

        user = User(
            email=email,
            password_hash=hash_password(password),
            name=name.strip(),
            year_level=year_level,
        )
        self.db.add(user)
        self.db.flush()
        token = self._issue_verification_token(user)
        self.db.commit()
        return user, token

    def _supersede_unused(self, rows) -> None:
        """Mark every still-open single-use token in `rows` as spent, so only
        the freshly issued one can be redeemed."""
        now = self.clock.now()
        for row in rows:
            if row.used_at is None:
                row.used_at = now

    def _issue_verification_token(self, user: User) -> str:
        self._supersede_unused(user.verification_tokens)
        now = self.clock.now()
        token = _new_token()
        self.db.add(
            EmailVerificationToken(
                user_id=user.id,
                token=token,
                expires_at=now + EMAIL_VERIFICATION_TTL,
                created_at=now,
            )
        )
        return token

    def verify_email(self, token: str) -> User:
        now = self.clock.now()
        row = self.db.scalar(
            select(EmailVerificationToken).where(EmailVerificationToken.token == token)
        )
        if _is_unusable(row, now):
            raise InvalidToken("verification token")
        row.used_at = now
        row.user.email_verified = True
        self.db.commit()
        return row.user

    def resend_verification(self, email: str) -> tuple[User, str] | None:
        """Fresh token + email for an unverified account. `None` when there is
        nothing to do (no such user, or already verified) — the router answers
        the same either way so an outsider can't probe registration."""
        email = email.strip().lower()
        user = self.db.scalar(select(User).where(User.email == email))
        if user is None or user.email_verified:
            return None
        token = self._issue_verification_token(user)
        self.db.commit()
        return user, token

    # -- login & sessions ----------------------------------------------------

    def _recent_failure_count(self, *, email: str | None, ip: str | None) -> int:
        window_start = self.clock.now() - LOGIN_FAILURE_WINDOW
        query = (
            select(func.count())
            .select_from(LoginAttempt)
            .where(
                LoginAttempt.succeeded.is_(False),
                LoginAttempt.created_at >= window_start,
            )
        )
        if email is not None:
            query = query.where(LoginAttempt.email == email)
            # A successful login for this email resets its counter: ignore any
            # failure that predates the latest success. (Ordering by row id, not
            # timestamp, so this holds even when the test clock is frozen.)
            last_ok_id = self.db.scalar(
                select(func.max(LoginAttempt.id)).where(
                    LoginAttempt.email == email, LoginAttempt.succeeded.is_(True)
                )
            )
            if last_ok_id is not None:
                query = query.where(LoginAttempt.id > last_ok_id)
        if ip is not None:
            query = query.where(LoginAttempt.ip == ip)
        return self.db.scalar(query)

    def _is_locked(self, *, email: str, ip: str) -> bool:
        if self._recent_failure_count(email=email, ip=None) >= LOGIN_MAX_FAILURES:
            return True
        return self._recent_failure_count(email=None, ip=ip) >= LOGIN_MAX_FAILURES_PER_IP

    def _record_attempt(self, email: str, ip: str, *, succeeded: bool) -> None:
        self.db.add(
            LoginAttempt(
                email=email,
                ip=ip,
                succeeded=succeeded,
                created_at=self.clock.now(),
            )
        )

    def authenticate(self, *, email: str, password: str, ip: str) -> User:
        email = email.strip().lower()

        if self._is_locked(email=email, ip=ip):
            # Don't log this as another failure — the window must be able to
            # clear on its own while the caller keeps knocking.
            raise AccountLocked(email)

        user = self.db.scalar(select(User).where(User.email == email))
        if user is None or not verify_password(password, user.password_hash):
            self._record_attempt(email, ip, succeeded=False)
            self.db.commit()
            raise InvalidCredentials(email)

        if not user.email_verified:
            # A genuine credential match, but not a usable login. Not counted
            # toward lockout.
            raise EmailNotVerified(email)

        self._record_attempt(email, ip, succeeded=True)
        self.db.commit()
        return user

    def issue_session(self, user: User) -> IssuedSession:
        now = self.clock.now()
        refresh = _new_token()
        self.db.add(
            RefreshToken(
                user_id=user.id,
                token=refresh,
                token_generation=user.token_generation,
                expires_at=now + REFRESH_TOKEN_TTL,
                created_at=now,
            )
        )
        self.db.commit()
        access = create_access_token(
            user_id=user.id, token_generation=user.token_generation, now=now
        )
        return IssuedSession(access_token=access, refresh_token=refresh)

    def _live_refresh_row(self, raw_token: str) -> RefreshToken:
        now = self.clock.now()
        row = self.db.scalar(
            select(RefreshToken).where(RefreshToken.token == raw_token)
        )
        if (
            row is None
            or row.revoked_at is not None
            or row.expires_at < now
            or row.token_generation != row.user.token_generation
        ):
            raise InvalidToken("refresh token")
        return row

    def rotate_refresh(self, raw_token: str) -> tuple[IssuedSession, User]:
        row = self._live_refresh_row(raw_token)
        row.revoked_at = self.clock.now()
        session = self.issue_session(row.user)
        return session, row.user

    def logout(self, raw_token: str | None) -> None:
        """End the current device's session. Idempotent — an unknown or already
        dead token is a no-op so a double logout still 'succeeds'."""
        if not raw_token:
            return
        row = self.db.scalar(
            select(RefreshToken).where(RefreshToken.token == raw_token)
        )
        if row is not None and row.revoked_at is None:
            row.revoked_at = self.clock.now()
            self.db.commit()

    def logout_all(self, user: User) -> None:
        user.token_generation += 1
        now = self.clock.now()
        for row in user.refresh_tokens:
            if row.revoked_at is None:
                row.revoked_at = now
        self.db.commit()

    # -- password recovery -------------------------------------------------

    def start_password_reset(self, email: str) -> tuple[User, str] | None:
        email = email.strip().lower()
        user = self.db.scalar(select(User).where(User.email == email))
        if user is None:
            return None
        self._supersede_unused(user.reset_tokens)
        now = self.clock.now()
        token = _new_token()
        self.db.add(
            PasswordResetToken(
                user_id=user.id,
                token=token,
                expires_at=now + PASSWORD_RESET_TTL,
                created_at=now,
            )
        )
        self.db.commit()
        return user, token

    def reset_password(self, *, token: str, new_password: str) -> User:
        now = self.clock.now()
        row = self.db.scalar(
            select(PasswordResetToken).where(PasswordResetToken.token == token)
        )
        if _is_unusable(row, now):
            raise InvalidToken("reset token")
        row.used_at = now
        user = row.user
        user.password_hash = hash_password(new_password)
        # Setting a new password ends every existing session (same mechanism as
        # "log out of all devices").
        user.token_generation += 1
        for refresh in user.refresh_tokens:
            if refresh.revoked_at is None:
                refresh.revoked_at = now
        self.db.commit()
        return user
