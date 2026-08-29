"""SQLAlchemy models.

Alembic is the schema source of truth (`migrations/`); this module is imported
by `migrations/env.py` so that `--autogenerate` sees every model's metadata.

Ticket 02 adds the auth tables: `User` plus the short-lived token tables
(`EmailVerificationToken`, `PasswordResetToken`, `RefreshToken`) and
`LoginAttempt` for login rate limiting. Ticket 03 adds the content tree
(`YearLevel` → `Subject` → `Unit` → `Topic`), the `topic_prerequisites`
association table, `LectureContent`, and the `TopicView` analytics event. The
practice/MentisQ tables arrive with their own tickets.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UtcDateTime

# Phase 1 registers students only. `ContentAdmin` is the one extra role this
# ticket needs — it can see draft content — and the `role` column already
# exists, so no migration is required to introduce it. `SuperAdmin` follows in
# ticket 06. `CONTEXT.md` is the term authority (never bare "Admin").
ROLE_STUDENT = "student"
ROLE_CONTENT_ADMIN = "content_admin"


def is_content_admin(user: "User") -> bool:
    """A `ContentAdmin` sees draft content that is hidden from students. Lives
    with the role constants; full role gating (`SuperAdmin` config endpoints)
    arrives with ticket 06."""
    return user.role == ROLE_CONTENT_ADMIN

# `LectureContent.status` values. A Topic is "published" to students when it
# has a `LectureContent` row in the `published` state; anything else is a draft
# and is invisible to students (visible to a `ContentAdmin`).
CONTENT_DRAFT = "draft"
CONTENT_PUBLISHED = "published"


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


# -- content tree ----------------------------------------------------------
#
# YearLevel → Subject → Unit → Topic, every level ordered. Phase 1 seeds one
# YearLevel ("Year 7"), one Subject ("Mathematics"). `order` is an admin-set
# integer used only for sorting siblings; it is not required to be dense or
# unique. See `CONTEXT.md` for what each level means.


class YearLevel(Base):
    __tablename__ = "year_levels"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    syllabus_region: Mapped[str] = mapped_column(String)

    subjects: Mapped[list[Subject]] = relationship(
        back_populates="year_level",
        cascade="all, delete-orphan",
        order_by="Subject.order",
    )


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True)
    year_level_id: Mapped[int] = mapped_column(
        ForeignKey("year_levels.id"), index=True
    )
    title: Mapped[str] = mapped_column(String)
    order: Mapped[int] = mapped_column(Integer)

    year_level: Mapped[YearLevel] = relationship(back_populates="subjects")
    units: Mapped[list[Unit]] = relationship(
        back_populates="subject",
        cascade="all, delete-orphan",
        order_by="Unit.order",
    )


class Unit(Base):
    __tablename__ = "units"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id"), index=True
    )
    title: Mapped[str] = mapped_column(String)
    order: Mapped[int] = mapped_column(Integer)

    subject: Mapped[Subject] = relationship(back_populates="units")
    topics: Mapped[list[Topic]] = relationship(
        back_populates="unit",
        cascade="all, delete-orphan",
        order_by="Topic.order",
    )


# Association table for the directed Topic → prerequisite Topic edges. A plain
# Core table (not an ORM entity) — it carries no columns of its own, and the
# seed ingest (ticket 05) appends rows through `Topic.prerequisites`.
topic_prerequisites = Table(
    "topic_prerequisites",
    Base.metadata,
    Column(
        "topic_id",
        ForeignKey("topics.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "prerequisite_topic_id",
        ForeignKey("topics.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    title: Mapped[str] = mapped_column(String)
    # Stable natural key: URLs reference a Topic by slug, and the seed ingest
    # upserts by it.
    slug: Mapped[str] = mapped_column(String, unique=True, index=True)
    order: Mapped[int] = mapped_column(Integer)

    unit: Mapped[Unit] = relationship(back_populates="topics")
    # One row per Topic (or none while it is being authored).
    lecture_content: Mapped[LectureContent | None] = relationship(
        back_populates="topic",
        cascade="all, delete-orphan",
        uselist=False,
    )
    prerequisites: Mapped[list[Topic]] = relationship(
        secondary=topic_prerequisites,
        primaryjoin=lambda: Topic.id == topic_prerequisites.c.topic_id,
        secondaryjoin=(
            lambda: Topic.id == topic_prerequisites.c.prerequisite_topic_id
        ),
        order_by="Topic.order",
    )


class LectureContent(Base):
    __tablename__ = "lecture_content"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id"), unique=True, index=True
    )
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default=CONTENT_DRAFT)
    # Bumped by the seed ingest when content is re-published; no edit history.
    version: Mapped[int] = mapped_column(Integer, default=1)

    topic: Mapped[Topic] = relationship(back_populates="lecture_content")


class TopicView(Base):
    """One row each time a student opens a Topic's lecture content. Write-only
    in Phase 1 — the student dashboard (ticket 07) reads it back as an activity
    signal.
    """

    __tablename__ = "topic_views"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), index=True
    )
