from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class MetaResponse(BaseModel):
    app: str
    environment: str
    server_time: datetime
    database: str


# -- auth ----------------------------------------------------------------

# NSW schooling runs Year 7-12; Phase 1 seeds Year 7 only but the field accepts
# the whole range so a Year 8 student isn't turned away at signup.
YearLevelField = Annotated[int, Field(ge=7, le=12)]
# bcrypt hashes at most 72 bytes of input, so a password is bounded there rather
# than silently truncated (see app/auth/passwords.py).
PasswordField = Annotated[str, Field(min_length=8, max_length=72)]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: PasswordField
    name: str = Field(min_length=1, max_length=120)
    year_level: YearLevelField


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    name: str
    year_level: int
    avatar_url: str | None
    role: str
    email_verified: bool


class MessageResponse(BaseModel):
    message: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfile


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1)
    new_password: PasswordField


class ProfileUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    avatar_url: str | None = Field(default=None, max_length=500)
    year_level: YearLevelField | None = None


# -- content tree ------------------------------------------------------------


class YearLevelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    syllabus_region: str


class SubjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    order: int


class UnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    order: int


class TopicRef(BaseModel):
    """A Topic as it appears in a list or as another Topic's prerequisite —
    enough to render a link, without the lecture body."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    slug: str
    order: int


class LectureContentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    body: str
    status: str
    version: int


class AnimationOut(BaseModel):
    """An attached animation as the Topic page renders it. `video_url` /
    `transcript_url` are resolved through the media seam (`/media/<key>`);
    `transcript_url` is null only on a draft with no transcript yet, which a
    student never sees (`status` is `draft` — a `ContentAdmin` preview)."""

    id: int
    slug: str
    title: str
    description: str
    status: str
    duration_seconds: int | None
    video_url: str
    transcript_url: str | None


class TopicDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    slug: str
    order: int
    unit_id: int
    # Absent only for a draft Topic with no content yet (ContentAdmin preview).
    lecture_content: LectureContentOut | None
    prerequisites: list[TopicRef]
    # Attached animations: published only for a student, plus drafts for a
    # `ContentAdmin`. Empty when the Topic has none.
    animations: list[AnimationOut]


class AnimationAdminOut(AnimationOut):
    """An animation as the ContentAdmin upload screen renders it — the
    student-facing view (`AnimationOut`) plus every Topic it is currently
    attached to. Draft rows are included; a student never sees this shape."""

    topics: list[TopicRef]


class SetAnimationTopicsRequest(BaseModel):
    """The complete set of Topics an animation should be attached to — the
    endpoint replaces the current set, so this both attaches and detaches."""

    topic_ids: list[int]


class AdminTopicOut(BaseModel):
    """Every Topic, flat, with its Unit/Subject/Year for grouping — the
    ContentAdmin screen's Topic picker reads this instead of walking the
    browse tree level by level."""

    id: int
    title: str
    slug: str
    unit_title: str
    subject_title: str
    year_level_name: str


# -- practice & grading -------------------------------------------------------


class StartPracticeRequest(BaseModel):
    topic_slug: str = Field(min_length=1)


class StartMixedPracticeRequest(BaseModel):
    # `unit` or `year_level` — what `scope_id` points at (a `units.id` or a
    # `year_levels.id`). Topic-scoped practice is the existing Topic flow.
    scope_type: str = Field(pattern="^(unit|year_level)$")
    scope_id: int = Field(ge=1)
    # Target size of the frozen set; a null falls back to the ≈ 10 default and
    # a scope with fewer eligible questions yields a smaller set.
    question_count: int | None = Field(default=None, ge=1, le=50)


class QuestionOptionOut(BaseModel):
    """An MCQ choice as the student sees it — no hint which one is correct."""

    id: str
    text: str


class PracticePartOut(BaseModel):
    """One sub-question of a `multi_part` question, as the student sees it —
    its stable `id`, `type`, optional prompt, and (for MCQ parts) options. No
    part carries its correct answer."""

    id: str
    type: str
    body: str | None
    options: list[QuestionOptionOut] | None


class PracticeQuestionOut(BaseModel):
    id: int
    type: str
    difficulty: str
    body: str
    # Present for mcq_single / mcq_multi; null otherwise.
    options: list[QuestionOptionOut] | None
    # Present for multi_part only; null otherwise.
    parts: list[PracticePartOut] | None


class PracticeSessionOut(BaseModel):
    topic: TopicRef
    questions: list[PracticeQuestionOut]


class MixedSessionOut(BaseModel):
    """A mixed practice run: a set sampled across a Unit / Year level at
    creation, then worked question-at-a-time with immediate feedback (like Topic
    practice — nothing is withheld). `scope_label` titles the run."""

    session_id: int
    mode: str
    scope_type: str
    scope_label: str
    questions: list[PracticeQuestionOut]


class SubmitAnswerRequest(BaseModel):
    # An option id (mcq_single), a list of option ids (mcq_multi), or a number
    # (numeric). Graded server-side; shape is validated by the grader, not here.
    answer: Any = None
    # Client-reported seconds spent before submitting.
    time_taken: int | None = Field(default=None, ge=0)


class SubmitAnswerResponse(BaseModel):
    # `null` while a `timed` quiz is still open — correctness is withheld until
    # the whole set is submitted for review.
    is_correct: bool | None
    attempt_no: int
    # The worked solution once `attempt_no` reaches the
    # `solution_reveal_after_attempts` Setting (default 1 — i.e. from the first
    # submission on, regardless of correctness); `null` before then, and always
    # `null` while a `timed` quiz is open.
    worked_solution: str | None
    # `timed` mode: `True` when this answer landed after the quiz's time limit
    # (accepted and stored anyway). `False` otherwise.
    after_time_limit: bool = False


class SolutionResponse(BaseModel):
    worked_solution: str


# -- timed quiz mode -------------------------------------------------------


class StartTimedQuizRequest(BaseModel):
    unit_id: int = Field(ge=1)


class UnitRef(BaseModel):
    """A Unit as the timed-quiz screen needs it — enough to title the quiz and
    link back."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    slug: str | None
    order: int


class TimedAnswerOut(BaseModel):
    """The student's latest stored answer for one question in an open quiz, so
    a page reload restores what they'd entered."""

    question_id: int
    submitted_answer: Any | None
    after_time_limit: bool


class SessionReviewQuestionOut(BaseModel):
    """One question in a submitted quiz's review: the public question plus the
    student's answer, its correctness, and the worked solution."""

    question: PracticeQuestionOut
    submitted_answer: Any | None
    # `null` when the student never answered it (scored incorrect).
    is_correct: bool | None
    after_time_limit: bool
    worked_solution: str


class SessionReviewOut(BaseModel):
    session_id: int
    mode: str
    # Proportion correct over the frozen set, 0.0–1.0 (unanswered = incorrect).
    score: float
    question_count: int
    submitted_at: datetime
    questions: list[SessionReviewQuestionOut]


class TimedSessionOut(BaseModel):
    """A timed quiz, open or submitted. While open: the frozen public questions,
    the server-authoritative countdown, and any answers so far. Once submitted:
    `review` is populated and `questions` / `answers` are empty."""

    session_id: int
    mode: str
    scope_type: str
    unit: UnitRef
    time_limit_seconds: int
    started_at: datetime
    # Whole seconds left by the server's `Clock`, never negative; 0 once the
    # limit has elapsed. The SPA counts down locally from this.
    remaining_seconds: int
    submitted_at: datetime | None
    questions: list[PracticeQuestionOut]
    answers: list[TimedAnswerOut]
    review: SessionReviewOut | None


# -- MentisQ (the AI tutor) ------------------------------------------------


class MentisQAskRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    # At most one context anchor. `topic_slug` for a lecture page, `question_id`
    # for a practice question; neither for a general maths question.
    topic_slug: str | None = Field(default=None, min_length=1)
    question_id: int | None = Field(default=None, ge=1)
    # Continue this conversation. Ignored if its context no longer matches the
    # anchor above (that opens a new session) or if `new_chat` is set.
    session_id: int | None = Field(default=None, ge=1)
    # Force a fresh session even when a prior one could be continued.
    new_chat: bool = False


class MentisQReplyOut(BaseModel):
    # Null only when a usage cap blocked the message before a session was made.
    session_id: int | None
    # The tutor's guided reply, the fixed fallback, or the fixed limit-reached
    # message — `status` says which.
    reply: str
    status: str  # "ok" | "failed" | "limit_reached"


class MentisQTurnOut(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class MentisQSessionOut(BaseModel):
    """A conversation and its non-failed turns, for the SPA to hydrate a running
    exchange (e.g. the general entry point resuming the latest chat)."""

    session_id: int
    topic_slug: str | None
    question_id: int | None
    helpful: bool | None
    turns: list[MentisQTurnOut]


class MentisQHelpfulRequest(BaseModel):
    # `null` clears a prior rating.
    helpful: bool | None = None


class MentisQSettingsOut(BaseModel):
    # Read-only here: the model id comes from `OPENROUTER_MODEL` in the
    # environment, not the database. The caps below are runtime-editable.
    model_name: str
    daily_message_cap: int
    per_student_monthly_cap_usd: float
    global_monthly_cap_usd: float | None


class MentisQSettingsUpdate(BaseModel):
    """Every field optional — only those present are written. Passing
    `global_monthly_cap_usd: null` explicitly clears the global ceiling.
    `model_name` is deliberately absent: it is environment-only."""

    daily_message_cap: int | None = Field(default=None, ge=0)
    per_student_monthly_cap_usd: float | None = Field(default=None, ge=0)
    global_monthly_cap_usd: float | None = Field(default=None, ge=0)


# -- student dashboard ---------------------------------------------------------


class DashboardAttemptOut(BaseModel):
    """One graded attempt in the student's recent history. Solution-only
    marker rows (`attempt_no = 0`) are not included."""

    id: int
    question_id: int
    topic_slug: str
    topic_title: str
    difficulty: str
    is_correct: bool
    attempt_no: int
    time_taken: int | None
    solution_viewed: bool
    created_at: datetime


class TopicPerformanceOut(BaseModel):
    """Percentage correct in one Topic, computed on read from the student's
    graded attempts (no `PerformanceSnapshot`, no recompute job)."""

    topic_slug: str
    topic_title: str
    # Graded attempt rows in this Topic, and how many were correct.
    attempts: int
    correct: int
    # correct / attempts x 100, rounded to one decimal place.
    percent_correct: float


class DashboardActivityOut(BaseModel):
    """Activity counts over the last `window_days` days (by the injected Clock)."""

    window_days: int
    topic_views: int
    topics_viewed: int  # distinct Topics opened
    mentisq_messages: int  # the student's `ok` MentisQ user turns


class SkillMasteryOut(BaseModel):
    """One SkillTag's cached mastery, from the last `PerformanceSnapshot`
    recompute. `mastery` is a 0–1 recency-weighted proportion correct;
    `insufficient_data` is set when fewer than three first attempts back it,
    so the dashboard can render it as "not enough data yet"."""

    skill_tag_id: int
    skill_tag_name: str
    mastery: float
    sample_size: int
    insufficient_data: bool


class TopicTrendOut(BaseModel):
    """One Topic's cached trend direction (`up` / `flat` / `down`), from the
    last `PerformanceSnapshot` recompute."""

    topic_slug: str
    topic_title: str
    trend: str


class RecommendationOut(BaseModel):
    """A "study this next" item. `reason` is `practice` (work the Topic itself)
    or `revise_prerequisite` (a prerequisite scores lower — revise it first),
    in which case `for_topic_*` names the weak Topic it unblocks. `mastery` is
    the recommended Topic's own cached mastery."""

    topic_slug: str
    topic_title: str
    reason: str
    mastery: float
    for_topic_slug: str | None = None
    for_topic_title: str | None = None


class StudentDashboardOut(BaseModel):
    recent_attempts: list[DashboardAttemptOut]
    topic_performance: list[TopicPerformanceOut]
    # The three cached-snapshot views (ticket 02). Empty until the recompute
    # job has run for the caller.
    skill_mastery: list[SkillMasteryOut]
    topic_trends: list[TopicTrendOut]
    recommendations: list[RecommendationOut]
    activity: DashboardActivityOut
