"""`/admin/...` — `SuperAdmin`-only system configuration.

Reached in the browser under `/api/admin/...` (the proxy strips `/api`).

Phase 1 exposes one resource: the MentisQ settings (model name + usage caps).
`require_super_admin` refuses every other caller with 403.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import require_super_admin
from app.database import get_db
from app.mentisq.settings import MentisQSettings
from app.models import User
from app.schemas import MentisQSettingsOut, MentisQSettingsUpdate

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/mentisq-settings", response_model=MentisQSettingsOut)
def read_mentisq_settings(
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
) -> dict:
    return MentisQSettings(db).as_dict()


@router.put("/mentisq-settings", response_model=MentisQSettingsOut)
def update_mentisq_settings(
    body: MentisQSettingsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
) -> dict:
    settings = MentisQSettings(db)
    settings.update(**body.model_dump(exclude_unset=True))
    db.commit()
    return settings.as_dict()
