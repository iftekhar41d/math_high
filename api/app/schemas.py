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


# -- practice & grading -------------------------------------------------------


class StartPracticeRequest(BaseModel):
    topic_slug: str = Field(min_length=1)


class QuestionOptionOut(BaseModel):
    """An MCQ choice as the student sees it — no hint which one is correct."""

    id: str
    text: str


class PracticeQuestionOut(BaseModel):
    id: int
    type: str
    difficulty: str
    body: str
    # Present for mcq_single / mcq_multi; null for numeric.
    options: list[QuestionOptionOut] | None


class PracticeSessionOut(BaseModel):
    topic: TopicRef
    questions: list[PracticeQuestionOut]


class SubmitAnswerRequest(BaseModel):
    # An option id (mcq_single), a list of option ids (mcq_multi), or a number
    # (numeric). Graded server-side; shape is validated by the grader, not here.
    answer: Any = None
    # Client-reported seconds spent before submitting.
    time_taken: int | None = Field(default=None, ge=0)


class SubmitAnswerResponse(BaseModel):
    is_correct: bool
    attempt_no: int
    # Returned from the first submission on, regardless of correctness.
    worked_solution: str


class SolutionResponse(BaseModel):
    worked_solution: str


# -- MentisQ (the AI tutor) ------------------------------------------------


class MentisQAskRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    # At most one context anchor. `topic_slug` for a lecture page, `question_id`
    # for a practice question; neither for a general maths question.
    topic_slug: str | None = Field(default=None, min_length=1)
    question_id: int | None = Field(default=None, ge=1)


class MentisQReplyOut(BaseModel):
    # Null only when a usage cap blocked the message before a session was made.
    session_id: int | None
    # The tutor's guided reply, the fixed fallback, or the fixed limit-reached
    # message — `status` says which.
    reply: str
    status: str  # "ok" | "failed" | "limit_reached"


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
