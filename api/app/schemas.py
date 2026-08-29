from datetime import datetime
from typing import Annotated

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
