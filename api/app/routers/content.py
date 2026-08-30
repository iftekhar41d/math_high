"""`/content/...` — browsing the course tree and reading a Topic's lecture.

Reached in the browser under `/api/content/...` (the proxy strips `/api`).

Every endpoint requires a verified caller. Students see only `published`
content; a `ContentAdmin` additionally sees drafts. Opening a Topic's lecture
content as a student records a `TopicView` (analytics); a `ContentAdmin`
previewing does not.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.animations import animation_out, visible_animations
from app.auth.dependencies import require_verified_user
from app.clock import Clock, get_clock
from app.content_access import topic_is_published as _is_published
from app.database import get_db
from app.models import (
    Subject,
    Topic,
    TopicView,
    Unit,
    User,
    YearLevel,
    is_content_admin,
)
from app.schemas import (
    LectureContentOut,
    SubjectOut,
    TopicDetail,
    TopicRef,
    UnitOut,
    YearLevelOut,
)
from app.storage import MediaStorage, get_media_storage

router = APIRouter(prefix="/content", tags=["content"])


def _not_found(what: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"No such {what}."
    )


def _get_or_404(db: Session, model, pk: int, what: str):
    obj = db.get(model, pk)
    if obj is None:
        raise _not_found(what)
    return obj


@router.get("/year-levels", response_model=list[YearLevelOut])
def list_year_levels(
    db: Session = Depends(get_db),
    _: User = Depends(require_verified_user),
) -> list[YearLevel]:
    # `YearLevel` has no `order` column (per the ticket schema); id order is
    # seed order, which is chronological by grade.
    return list(db.scalars(select(YearLevel).order_by(YearLevel.id)))


@router.get(
    "/year-levels/{year_level_id}/subjects", response_model=list[SubjectOut]
)
def list_subjects(
    year_level_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_verified_user),
) -> list[Subject]:
    _get_or_404(db, YearLevel, year_level_id, "year level")
    return list(
        db.scalars(
            select(Subject)
            .where(Subject.year_level_id == year_level_id)
            .order_by(Subject.order)
        )
    )


@router.get("/subjects/{subject_id}/units", response_model=list[UnitOut])
def list_units(
    subject_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_verified_user),
) -> list[Unit]:
    _get_or_404(db, Subject, subject_id, "subject")
    return list(
        db.scalars(
            select(Unit)
            .where(Unit.subject_id == subject_id)
            .order_by(Unit.order)
        )
    )


@router.get("/units/{unit_id}/topics", response_model=list[TopicRef])
def list_topics(
    unit_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_verified_user),
) -> list[Topic]:
    _get_or_404(db, Unit, unit_id, "unit")
    topics = list(
        db.scalars(
            select(Topic).where(Topic.unit_id == unit_id).order_by(Topic.order)
        )
    )
    if is_content_admin(user):
        return topics
    return [t for t in topics if _is_published(t)]


@router.get("/topics/{slug}", response_model=TopicDetail)
def get_topic(
    slug: str,
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    storage: MediaStorage = Depends(get_media_storage),
    user: User = Depends(require_verified_user),
) -> TopicDetail:
    topic = db.scalar(select(Topic).where(Topic.slug == slug))
    if topic is None:
        raise _not_found("topic")

    admin = is_content_admin(user)
    if not admin and not _is_published(topic):
        # A draft Topic simply does not exist as far as a student is concerned.
        raise _not_found("topic")

    prerequisites = topic.prerequisites
    lecture = topic.lecture_content
    animations = [
        animation_out(a, storage)
        for a in visible_animations(topic, include_drafts=admin)
    ]
    if not admin:
        prerequisites = [p for p in prerequisites if _is_published(p)]
        # Reading the lecture is the analytics event.
        db.add(
            TopicView(
                user_id=user.id, topic_id=topic.id, created_at=clock.now()
            )
        )
        db.commit()

    return TopicDetail(
        id=topic.id,
        title=topic.title,
        slug=topic.slug,
        order=topic.order,
        unit_id=topic.unit_id,
        lecture_content=(
            LectureContentOut.model_validate(lecture)
            if lecture is not None
            else None
        ),
        prerequisites=[TopicRef.model_validate(p) for p in prerequisites],
        animations=animations,
    )
