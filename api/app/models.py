"""SQLAlchemy models.

Alembic is the schema source of truth (`migrations/`); this module is imported
by `migrations/env.py` so that `--autogenerate` sees every model's metadata.

Ticket 02 adds the auth tables: `User` plus the short-lived token tables
(`EmailVerificationToken`, `PasswordResetToken`, `RefreshToken`) and
`LoginAttempt` for login rate limiting. Ticket 03 adds the content tree
(`YearLevel` → `Subject` → `Unit` → `Topic`), the `topic_prerequisites`
association table, `LectureContent`, and the `TopicView` analytics event. The
Ticket 04 adds the practice tables: `Question` (with its `answer_schema` JSON),
`SkillTag` + the `question_skill_tags` association table, and `QuestionAttempt`.
Ticket 06 adds the MentisQ tables (`MentisQSession`, `MentisQMessage`) and the
`Setting` key/value store for `SuperAdmin` configuration.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UtcDateTime

# Phase 1 registers students only. `ContentAdmin` sees draft content;
# `SuperAdmin` manages system configuration (MentisQ model + usage caps). The
# `role` column already exists, so introducing either is migration-free.
# `CONTEXT.md` is the term authority (never bare "Admin").
ROLE_STUDENT = "student"
ROLE_CONTENT_ADMIN = "content_admin"
ROLE_SUPER_ADMIN = "super_admin"


def is_content_admin(user: "User") -> bool:
    """A `ContentAdmin` sees draft content that is hidden from students."""
    return user.role == ROLE_CONTENT_ADMIN


def is_super_admin(user: "User") -> bool:
    """A `SuperAdmin` reads and writes system configuration — the MentisQ model
    name and the usage caps (ticket 06)."""
    return user.role == ROLE_SUPER_ADMIN

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


# The `slug` on every level below is the stable natural key the seed ingest
# (ticket 05) upserts by: re-running the ingest matches rows by slug and updates
# them in place rather than inserting duplicates. Nullable only so the column
# could be added to a populated database without a backfill; the ingest always
# sets it, and nothing else creates these rows in Phase 1.


class YearLevel(Base):
    __tablename__ = "year_levels"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str | None] = mapped_column(
        String, unique=True, index=True, nullable=True
    )
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
    slug: Mapped[str | None] = mapped_column(
        String, unique=True, index=True, nullable=True
    )
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
    slug: Mapped[str | None] = mapped_column(
        String, unique=True, index=True, nullable=True
    )
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


# -- practice & grading --------------------------------------------------
#
# A Topic's practice questions. Grading is entirely server-side: `answer_schema`
# holds the correct answer keyed by `type`, and is NEVER serialised to a student
# — `app/practice/payload.py` is the single chokepoint that builds the public
# view (body, difficulty, and MCQ option text only).

QUESTION_MCQ_SINGLE = "mcq_single"
QUESTION_MCQ_MULTI = "mcq_multi"
QUESTION_NUMERIC = "numeric"

DIFFICULTY_EASY = "easy"
DIFFICULTY_MEDIUM = "medium"
DIFFICULTY_HARD = "hard"


# Many-to-many Question ↔ SkillTag, for per-skill analytics aggregation. Plain
# Core table; the seed ingest (ticket 05) appends through `Question.skill_tags`.
question_skill_tags = Table(
    "question_skill_tags",
    Base.metadata,
    Column(
        "question_id",
        ForeignKey("questions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "skill_tag_id",
        ForeignKey("skill_tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class SkillTag(Base):
    __tablename__ = "skill_tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stable natural key the seed ingest upserts by (see the note above
    # `YearLevel`). Nullable for the same reason.
    slug: Mapped[str | None] = mapped_column(
        String, unique=True, index=True, nullable=True
    )
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    # One of QUESTION_* above.
    type: Mapped[str] = mapped_column(String)
    # One of DIFFICULTY_* above; shown to the student so they know what to expect.
    difficulty: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text)
    # Discriminated by `type`:
    #   mcq_single: {"options": [{"id","text"}, ...], "correct_option": "b"}
    #   mcq_multi:  {"options": [...], "correct_options": ["a", "c"]}
    #   numeric:    {"value": 3.14, "tolerance": 0.01}
    # The `correct_*` / `value` / `tolerance` keys never leave the server.
    answer_schema: Mapped[dict[str, Any]] = mapped_column(JSON)
    worked_solution: Mapped[str] = mapped_column(Text)

    topic: Mapped[Topic] = relationship()
    skill_tags: Mapped[list[SkillTag]] = relationship(
        secondary=question_skill_tags,
        order_by="SkillTag.name",
    )


class QuestionAttempt(Base):
    """One row per graded submission. A bare "show solution" with no prior
    submission also writes a marker row (`attempt_no = 0`, `submitted_answer`
    and `is_correct` null) so the view is still recorded. The student dashboard
    (ticket 07) reads these back.
    """

    __tablename__ = "question_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id"), index=True
    )
    # The student's answer as submitted (option id, list of ids, or number);
    # null on a solution-only marker row.
    submitted_answer: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Client-reported seconds on the question before this submission.
    time_taken: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 1 for the first graded submission, 2 for the next…; 0 for a marker row.
    attempt_no: Mapped[int] = mapped_column(Integer, default=0)
    hints_used: Mapped[int] = mapped_column(Integer, default=0)
    mentisq_used: Mapped[bool] = mapped_column(Boolean, default=False)
    solution_viewed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), index=True
    )


# -- MentisQ (the AI tutor) --------------------------------------------------
#
# A `MentisQSession` is one tutoring conversation belonging to a student,
# optionally scoped to the Topic or Question it was launched from. Phase 1 UX is
# a single exchange (one user turn + one assistant turn) and `mode` is always
# `guided`, but the schema keeps a full message log from day one. Each
# `MentisQMessage` carries the token usage and USD cost reported by the
# provider — that is what the daily-message and monthly-spend caps read back.

MENTISQ_MODE_GUIDED = "guided"

MENTISQ_ROLE_USER = "user"
MENTISQ_ROLE_ASSISTANT = "assistant"

# `ok` messages count toward the usage caps; a `failed` turn (provider timeout /
# outage / bad response) is stored for the record but metered against nothing.
MENTISQ_STATUS_OK = "ok"
MENTISQ_STATUS_FAILED = "failed"


class MentisQSession(Base):
    __tablename__ = "mentisq_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # At most one of these is set — the Topic or the Question the student asked
    # from. Null for a general maths question.
    context_topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id"), nullable=True
    )
    context_question_id: Mapped[int | None] = mapped_column(
        ForeignKey("questions.id"), nullable=True
    )
    mode: Mapped[str] = mapped_column(String, default=MENTISQ_MODE_GUIDED)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), index=True
    )

    messages: Mapped[list[MentisQMessage]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="MentisQMessage.id",
    )


class MentisQMessage(Base):
    __tablename__ = "mentisq_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("mentisq_sessions.id"), index=True
    )
    # MENTISQ_ROLE_* — the student's turn or the tutor's.
    role: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    # MENTISQ_STATUS_* — `failed` marks a turn the provider did not complete.
    status: Mapped[str] = mapped_column(String, default=MENTISQ_STATUS_OK)
    # Usage from the provider's response, split across the pair: prompt tokens on
    # the user turn, completion tokens + `cost_usd` on the assistant turn. So
    # every row's usage is real and `SUM(cost_usd)` counts each exchange once.
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), index=True
    )

    session: Mapped[MentisQSession] = relationship(back_populates="messages")


class Setting(Base):
    """A tiny key/value store for `SuperAdmin`-managed system configuration.
    Values are stored as strings; `app/mentisq/settings.py` and
    `app/analytics/settings.py` own the typed accessors and the in-code
    defaults used when a key is absent.
    """

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)


# -- performance snapshots (analytics) -------------------------------------
#
# Cached mastery figures, rebuilt out-of-band by
# `python -m app.analytics.recompute` from the `QuestionAttempt` / `TopicView`
# history the platform already stores. Nothing on the request path writes here;
# the student dashboard reads these rows back.

SNAPSHOT_DIMENSION_TOPIC = "topic"
SNAPSHOT_DIMENSION_SKILL_TAG = "skill_tag"

TREND_UP = "up"
TREND_FLAT = "flat"
TREND_DOWN = "down"

# Fewer contributing first attempts than this and a snapshot's `mastery` is too
# thin to show as a number — the dashboard renders "not enough data yet"
# instead. The recompute still writes the row (see `PerformanceSnapshot`).
SNAPSHOT_MIN_CONFIDENT_SAMPLE = 3


class PerformanceSnapshot(Base):
    """One student's cached mastery along one dimension — a Topic or a
    SkillTag they have attempted. `mastery` is a recency-weighted proportion
    correct over the first graded attempt of each Question, `trend` is the
    bucketed direction of change across the last two 30-day windows, and
    `sample_size` is the number of contributing first attempts (the row is
    written even when it is below 3). One row per (user, dimension,
    dimension_id); `computed_at` stamps the recompute that produced it.
    """

    __tablename__ = "performance_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # SNAPSHOT_DIMENSION_* — what `dimension_id` points at.
    dimension: Mapped[str] = mapped_column(String)
    # A `topics.id` or a `skill_tags.id`, per `dimension`. Not a ForeignKey:
    # the column is polymorphic across two tables.
    dimension_id: Mapped[int] = mapped_column(Integer)
    mastery: Mapped[float] = mapped_column(Float)
    # TREND_* — direction of recent change.
    trend: Mapped[str] = mapped_column(String)
    sample_size: Mapped[int] = mapped_column(Integer)
    computed_at: Mapped[datetime] = mapped_column(UtcDateTime)

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "dimension",
            "dimension_id",
            name="uq_performance_snapshots_user_dimension",
        ),
    )
