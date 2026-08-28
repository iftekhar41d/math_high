"""HTTP layer for auth. Every endpoint is a thin wrapper over `AuthService`;
this module owns status codes, the refresh cookie, and the outbound emails.

Reached in the browser under `/api/auth/...` (the proxy strips `/api`).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.auth.config import (
    REFRESH_COOKIE_NAME,
    REFRESH_TOKEN_TTL,
    cookie_secure,
    public_base_url,
)
from app.auth.dependencies import get_auth_service, get_current_user
from app.auth.service import (
    AccountLocked,
    AuthService,
    EmailAlreadyRegistered,
    EmailNotVerified,
    InvalidCredentials,
    InvalidToken,
)
from app.email_sender import EmailMessage, EmailSender, get_email_sender
from app.models import User
from app.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserProfile,
    VerifyEmailRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_GENERIC_EMAIL_SENT = MessageResponse(
    message="If that email is registered, a message is on its way."
)


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=int(REFRESH_TOKEN_TTL.total_seconds()),
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        path="/",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        path="/",
    )


def _send_link_email(
    email: EmailSender, *, to: str, subject: str, path: str, token: str, intro: str
) -> None:
    link = f"{public_base_url()}/{path}?token={token}"
    email.send(EmailMessage(to=to, subject=subject, body=f"{intro}\n\n{link}\n"))


def _send_verification_email(email: EmailSender, to: str, token: str) -> None:
    _send_link_email(
        email,
        to=to,
        subject="Verify your MentisQ email",
        path="verify-email",
        token=token,
        intro="Welcome to MentisQ. Confirm your email address:",
    )


def _send_reset_email(email: EmailSender, to: str, token: str) -> None:
    _send_link_email(
        email,
        to=to,
        subject="Reset your MentisQ password",
        path="reset-password",
        token=token,
        intro="Use this link to set a new password:",
    )


@router.post(
    "/register",
    response_model=UserProfile,
    status_code=status.HTTP_201_CREATED,
)
def register(
    body: RegisterRequest,
    auth: AuthService = Depends(get_auth_service),
    email: EmailSender = Depends(get_email_sender),
) -> User:
    try:
        user, token = auth.register(
            email=body.email,
            password=body.password,
            name=body.name,
            year_level=body.year_level,
        )
    except EmailAlreadyRegistered:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That email is already registered.",
        )
    _send_verification_email(email, user.email, token)
    return user


@router.post("/verify-email", response_model=MessageResponse)
def verify_email(
    body: VerifyEmailRequest, auth: AuthService = Depends(get_auth_service)
) -> MessageResponse:
    try:
        auth.verify_email(body.token)
    except InvalidToken:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That verification link is invalid or has expired.",
        )
    return MessageResponse(message="Email verified. You can log in now.")


@router.post("/resend-verification", response_model=MessageResponse)
def resend_verification(
    body: ResendVerificationRequest,
    auth: AuthService = Depends(get_auth_service),
    email: EmailSender = Depends(get_email_sender),
) -> MessageResponse:
    result = auth.resend_verification(body.email)
    if result is not None:
        user, token = result
        _send_verification_email(email, user.email, token)
    return _GENERIC_EMAIL_SENT


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    ip = request.client.host if request.client else "unknown"
    try:
        user = auth.authenticate(email=body.email, password=body.password, ip=ip)
    except AccountLocked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Try again later.",
        )
    except EmailNotVerified:
        # The SPA treats any 403 from /auth/login as "unverified" and offers a
        # resend; a plain string keeps the error contract uniform.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verify your email before logging in.",
        )
    except InvalidCredentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    session = auth.issue_session(user)
    _set_refresh_cookie(response, session.refresh_token)
    return TokenResponse(access_token=session.access_token, user=user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    presented = request.cookies.get(REFRESH_COOKIE_NAME)
    if not presented:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh session."
        )
    try:
        session, user = auth.rotate_refresh(presented)
    except InvalidToken:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh session is no longer valid.",
        )
    _set_refresh_cookie(response, session.refresh_token)
    return TokenResponse(access_token=session.access_token, user=user)


@router.post("/logout", response_model=MessageResponse)
def logout(
    request: Request,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    auth.logout(request.cookies.get(REFRESH_COOKIE_NAME))
    _clear_refresh_cookie(response)
    return MessageResponse(message="Logged out.")


@router.post("/logout-all", response_model=MessageResponse)
def logout_all(
    response: Response,
    auth: AuthService = Depends(get_auth_service),
    user: User = Depends(get_current_user),
) -> MessageResponse:
    auth.logout_all(user)
    _clear_refresh_cookie(response)
    return MessageResponse(message="Logged out of all devices.")


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    body: ForgotPasswordRequest,
    auth: AuthService = Depends(get_auth_service),
    email: EmailSender = Depends(get_email_sender),
) -> MessageResponse:
    result = auth.start_password_reset(body.email)
    if result is not None:
        user, token = result
        _send_reset_email(email, user.email, token)
    return _GENERIC_EMAIL_SENT


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(
    body: ResetPasswordRequest,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    try:
        auth.reset_password(token=body.token, new_password=body.new_password)
    except InvalidToken:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That reset link is invalid or has expired.",
        )
    _clear_refresh_cookie(response)
    return MessageResponse(message="Password updated. Log in with your new password.")
