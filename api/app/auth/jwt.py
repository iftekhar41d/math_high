"""Access-token minting and decoding.

The access token is a short-lived HS256 JWT the SPA holds in memory. It carries
the user id and the `token_generation` it was minted under; `get_current_user`
rejects it once the user's generation moves on (password reset, logout-all), so
those actions kill live access tokens too, not just refresh tokens.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import jwt

from app.auth.config import ACCESS_TOKEN_TTL, JWT_ALGORITHM, jwt_secret


@dataclass(frozen=True)
class AccessClaims:
    user_id: int
    token_generation: int


class InvalidAccessToken(Exception):
    pass


def create_access_token(*, user_id: int, token_generation: int, now: datetime) -> str:
    payload = {
        "sub": str(user_id),
        "gen": token_generation,
        "iat": int(now.timestamp()),
        "exp": int((now + ACCESS_TOKEN_TTL).timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, *, now: datetime) -> AccessClaims:
    """Verify signature and claim shape, then check expiry against `now` (the
    injected clock) rather than wall time, so the test suite can expire a token
    by advancing its fake clock."""
    try:
        payload = jwt.decode(
            token,
            jwt_secret(),
            algorithms=[JWT_ALGORITHM],
            options={"verify_exp": False},
        )
    except jwt.PyJWTError as exc:
        raise InvalidAccessToken(str(exc)) from exc
    if payload.get("type") != "access":
        raise InvalidAccessToken("wrong token type")
    try:
        exp = int(payload["exp"])
        claims = AccessClaims(
            user_id=int(payload["sub"]), token_generation=int(payload["gen"])
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise InvalidAccessToken("malformed claims") from exc
    if now.timestamp() >= exp:
        raise InvalidAccessToken("expired")
    return claims
