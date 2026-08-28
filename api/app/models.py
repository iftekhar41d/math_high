"""SQLAlchemy models.

Alembic is the schema source of truth (`migrations/`); this module is imported
by `migrations/env.py` so that `--autogenerate` sees every model's metadata.

Ticket 02 adds the auth tables: `User` plus the short-lived token tables
(`EmailVerificationToken`, `PasswordResetToken`, `RefreshToken`) and
`LoginAttempt` for login rate limiting. The content/practice/MentisQ tables
arrive with their own tickets.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UtcDateTime

# Phase 1 only registers students. The column exists so ticket 06 can add the
# admin roles without a migration; `CONTEXT.md` is the term authority
# (`ContentAdmin` / `SuperAdmin`, never bare "Admin") when those land.
ROLE_STUDENT = "student"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    # Nullable so a future OAuth identity is purely additive (spec §"Data model").
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String)
    year_level: Mapped[int] = mapped_column(Integer)
    avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, default=ROLE_STUDENT)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    # Bumped by "log out of all devices" / password reset; every access and
    # refresh token carries the generation it was minted under and is rejected
    # once it falls behind.
    token_generation: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now()
    )

    verification_tokens: Mapped[list[EmailVerificationToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    reset_tokens: Mapped[list[PasswordResetToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class _SingleUseToken:
    """Shared columns for the email-verification and password-reset tokens: an
    opaque secret, an expiry, and a `used_at` stamp set when it's consumed.
    Subclasses add `__tablename__` and the `user` relationship.
    """

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token: Mapped[str] = mapped_column(String, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now()
    )


class EmailVerificationToken(_SingleUseToken, Base):
    __tablename__ = "email_verification_tokens"

    user: Mapped[User] = relationship(back_populates="verification_tokens")


class PasswordResetToken(_SingleUseToken, Base):
    __tablename__ = "password_reset_tokens"

    user: Mapped[User] = relationship(back_populates="reset_tokens")


class RefreshToken(Base):
    """One row per issued refresh token. Rotation revokes the presented row and
    inserts a fresh one; `logout-all` is enforced via `User.token_generation`,
    so old rows don't all need touching on that path.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token: Mapped[str] = mapped_column(String, unique=True, index=True)
    token_generation: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(
        UtcDateTime, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens")


class LoginAttempt(Base):
    """Every login try, success or failure. Read back as a windowed count of
    failures — per email, and (with a looser limit) per IP — to decide lockout.
    A successful attempt resets the window for that email.
    """

    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String, index=True)
    ip: Mapped[str] = mapped_column(String, index=True)
    succeeded: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), index=True
    )
