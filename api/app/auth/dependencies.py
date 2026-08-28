"""FastAPI dependencies for the authenticated caller.

`get_current_user` turns a bearer access token into a `User`, rejecting it if
the signature/expiry is bad or if the user's `token_generation` has moved past
the value baked into the token (password reset, logout-all).
`require_verified_user` additionally insists the email is confirmed — that is the
gate every student endpoint should sit behind. Role-gated dependencies arrive
with the admin endpoints (ticket 06).
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.jwt import InvalidAccessToken, decode_access_token
from app.auth.service import AuthService
from app.clock import Clock, get_clock
from app.database import get_db
from app.models import User

_UNAUTH = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_auth_service(
    db: Session = Depends(get_db), clock: Clock = Depends(get_clock)
) -> AuthService:
    return AuthService(db, clock)


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _UNAUTH
    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = decode_access_token(token, now=clock.now())
    except InvalidAccessToken:
        raise _UNAUTH

    user = db.get(User, claims.user_id)
    if user is None or user.token_generation != claims.token_generation:
        raise _UNAUTH
    return user


def require_verified_user(user: User = Depends(get_current_user)) -> User:
    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Email not verified"
        )
    return user
