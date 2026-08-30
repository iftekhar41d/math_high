"""`/content-admin/...` — ContentAdmin-only animation authoring.

Reached in the browser under `/api/content-admin/...` (the proxy strips
`/api`). Every endpoint is gated by `require_content_admin`; a student or a
`SuperAdmin` gets 403. This is the only path that creates `Animation` rows —
the text-only manifest ingest never does (`app/animations.py`).

The flow the ContentAdmin upload screen drives: `POST /animations` uploads the
video (+ optional transcript) and upserts the row by `slug`; `PUT
/animations/{slug}/topics` sets the Topics it is attached to (replacing the
current set — it both attaches and detaches); `POST /animations/{slug}/publish`
/ `.../unpublish` toggle draft ⇄ published, with the shared rule that
publishing needs a transcript (`app/animations.py::publish_animation`).
"""

from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.animations import (
    CannotPublish,
    admin_animation_out,
    media_key_for,
    publish_animation,
    unpublish_animation,
)
from app.auth.dependencies import require_content_admin
from app.database import get_db
from app.models import Animation, Subject, Topic, Unit, User, YearLevel
from app.schemas import (
    AdminTopicOut,
    AnimationAdminOut,
    SetAnimationTopicsRequest,
)
from app.storage import MediaStorage, get_media_storage

router = APIRouter(prefix="/content-admin", tags=["content-admin"])


def _get_animation_or_404(db: Session, slug: str) -> Animation:
    animation = db.scalar(select(Animation).where(Animation.slug == slug))
    if animation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No such animation: {slug!r}.",
        )
    return animation


@router.get("/topics", response_model=list[AdminTopicOut])
def list_topics(
    db: Session = Depends(get_db),
    _: User = Depends(require_content_admin),
) -> list[AdminTopicOut]:
    """Every Topic in the course, flat, for the upload screen's Topic picker."""
    rows = db.execute(
        select(Topic, Unit, Subject, YearLevel)
        .join(Unit, Topic.unit_id == Unit.id)
        .join(Subject, Unit.subject_id == Subject.id)
        .join(YearLevel, Subject.year_level_id == YearLevel.id)
        .order_by(YearLevel.id, Subject.order, Unit.order, Topic.order)
    )
    return [
        AdminTopicOut(
            id=topic.id,
            title=topic.title,
            slug=topic.slug,
            unit_title=unit.title,
            subject_title=subject.title,
            year_level_name=year_level.name,
        )
        for topic, unit, subject, year_level in rows
    ]


@router.get("/animations", response_model=list[AnimationAdminOut])
def list_animations(
    db: Session = Depends(get_db),
    storage: MediaStorage = Depends(get_media_storage),
    _: User = Depends(require_content_admin),
) -> list[AnimationAdminOut]:
    rows = db.scalars(select(Animation).order_by(Animation.id))
    return [admin_animation_out(a, storage) for a in rows]


@router.get("/animations/{slug}", response_model=AnimationAdminOut)
def get_animation(
    slug: str,
    db: Session = Depends(get_db),
    storage: MediaStorage = Depends(get_media_storage),
    _: User = Depends(require_content_admin),
) -> AnimationAdminOut:
    return admin_animation_out(_get_animation_or_404(db, slug), storage)


# Same shape the manifest ingest enforces (`app/ingest/manifest.py`): lowercase
# letters / digits joined by single hyphens. Keeps a stray `/` or `..` out of
# `media_key_for` (which would otherwise blow up in `LocalMediaStorage`).
_SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


@router.post("/animations", response_model=AnimationAdminOut)
def upsert_animation(
    response: Response,
    slug: str = Form(pattern=_SLUG_PATTERN),
    title: str = Form(min_length=1),
    description: str = Form(""),
    duration_seconds: int | None = Form(default=None, ge=0),
    video: UploadFile | None = File(default=None),
    transcript: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    storage: MediaStorage = Depends(get_media_storage),
    _: User = Depends(require_content_admin),
) -> AnimationAdminOut:
    """Create or update the animation with this `slug`. A new row needs a
    `video`; an update keeps the stored video/transcript unless a fresh file is
    sent. Always lands as a `draft` on create — publishing is a separate step.
    """
    animation = db.scalar(select(Animation).where(Animation.slug == slug))
    creating = animation is None
    if creating and video is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="a new animation needs a video file.",
        )

    if creating:
        animation = Animation(slug=slug, video_key="")
        db.add(animation)

    animation.title = title
    animation.description = description or ""
    animation.duration_seconds = duration_seconds

    if video is not None:
        key = media_key_for(slug, "video", video.filename)
        storage.save(key, video.file)
        animation.video_key = key
    if transcript is not None:
        key = media_key_for(slug, "transcript", transcript.filename)
        storage.save(key, transcript.file)
        animation.transcript_key = key

    db.commit()
    response.status_code = (
        status.HTTP_201_CREATED if creating else status.HTTP_200_OK
    )
    return admin_animation_out(animation, storage)


@router.put("/animations/{slug}/topics", response_model=AnimationAdminOut)
def set_animation_topics(
    slug: str,
    body: SetAnimationTopicsRequest,
    db: Session = Depends(get_db),
    storage: MediaStorage = Depends(get_media_storage),
    _: User = Depends(require_content_admin),
) -> AnimationAdminOut:
    """Attach `animation` to exactly `topic_ids` — Topics dropped from the list
    are detached. Order and duplicates in the request don't matter; the stored
    order is `Topic.order` (the relationship's `order_by`)."""
    animation = _get_animation_or_404(db, slug)

    topics: list[Topic] = []
    for topic_id in dict.fromkeys(body.topic_ids):
        topic = db.get(Topic, topic_id)
        if topic is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No such topic: {topic_id}.",
            )
        topics.append(topic)

    animation.topics = topics
    db.commit()
    return admin_animation_out(animation, storage)


@router.post("/animations/{slug}/publish", response_model=AnimationAdminOut)
def publish(
    slug: str,
    db: Session = Depends(get_db),
    storage: MediaStorage = Depends(get_media_storage),
    _: User = Depends(require_content_admin),
) -> AnimationAdminOut:
    animation = _get_animation_or_404(db, slug)
    try:
        publish_animation(animation)
    except CannotPublish as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        )
    db.commit()
    return admin_animation_out(animation, storage)


@router.post("/animations/{slug}/unpublish", response_model=AnimationAdminOut)
def unpublish(
    slug: str,
    db: Session = Depends(get_db),
    storage: MediaStorage = Depends(get_media_storage),
    _: User = Depends(require_content_admin),
) -> AnimationAdminOut:
    animation = _get_animation_or_404(db, slug)
    unpublish_animation(animation)
    db.commit()
    return admin_animation_out(animation, storage)
