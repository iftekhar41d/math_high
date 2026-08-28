"""`/profile` — the authenticated student's own record.

Read and edit only; there is no admin user management in Phase 1. The caller
must be verified (`require_verified_user`), matching every other student-facing
endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import require_verified_user
from app.database import get_db
from app.models import User
from app.schemas import ProfileUpdateRequest, UserProfile

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=UserProfile)
def get_profile(user: User = Depends(require_verified_user)) -> User:
    return user


@router.patch("", response_model=UserProfile)
def update_profile(
    body: ProfileUpdateRequest,
    user: User = Depends(require_verified_user),
    db: Session = Depends(get_db),
) -> User:
    updates = body.model_dump(exclude_unset=True)
    # name / year_level can't be nulled out; avatar_url can (clearing an avatar).
    for field in ("name", "year_level"):
        if updates.get(field) is not None:
            setattr(user, field, updates[field])
    if "avatar_url" in updates:
        user.avatar_url = updates["avatar_url"]
    db.commit()
    db.refresh(user)
    return user
