"""`/meta` — the walking-skeleton endpoint.

It has no domain payload yet; it exists so the SPA shell can make one real
web -> nginx -> API -> DB round trip, and so the `Clock` and DB-session
dependencies are exercised end to end.
"""

import os

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.clock import Clock, get_clock
from app.database import get_db
from app.schemas import MetaResponse

router = APIRouter(tags=["meta"])


@router.get("/meta", response_model=MetaResponse)
def get_meta(
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> MetaResponse:
    db.execute(text("SELECT 1"))
    return MetaResponse(
        app="MentisQ",
        environment=os.getenv("APP_ENV", "development"),
        server_time=clock.now(),
        database="ok",
    )
