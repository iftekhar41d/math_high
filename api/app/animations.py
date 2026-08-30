"""Animation visibility, the publish gate, and the student-facing view.

An `Animation` is many-to-many with `Topic` (`animation_topics`). A student sees
only `published` animations attached to a Topic; a `ContentAdmin` also sees
drafts — the same split as `LectureContent` (`app/content_access.py`).
Publishing requires a transcript asset: `publish_animation` refuses a draft
without one. `animation_out` is the single place the stored row plus its
`MediaStorage` keys become the wire DTO (`/media/<key>` URLs). The
student-facing content router and the ContentAdmin upload screen (Phase 2
ticket 11) both build on these, so they live here rather than being
reimplemented in each.
"""

from __future__ import annotations

from app.models import CONTENT_PUBLISHED, Animation, Topic
from app.schemas import AnimationOut
from app.storage import MediaStorage


class CannotPublish(ValueError):
    """`publish_animation` was called on an animation with no transcript."""


def animation_is_published(animation: Animation) -> bool:
    return animation.status == CONTENT_PUBLISHED


def visible_animations(
    topic: Topic, *, include_drafts: bool
) -> list[Animation]:
    """`topic`'s attached animations for one audience: every `published` one,
    plus drafts when `include_drafts` is set (a `ContentAdmin`). Creation
    order, as `Topic.animations` already sorts by id."""
    return [
        a
        for a in topic.animations
        if include_drafts or animation_is_published(a)
    ]


def animation_out(animation: Animation, storage: MediaStorage) -> AnimationOut:
    """The student-facing view of `animation`: its metadata plus `video_key` /
    `transcript_key` resolved to public URLs through the media seam.
    `transcript_url` is null when no transcript has been uploaded yet."""
    return AnimationOut(
        id=animation.id,
        slug=animation.slug,
        title=animation.title,
        description=animation.description,
        status=animation.status,
        duration_seconds=animation.duration_seconds,
        video_url=storage.get_url(animation.video_key),
        transcript_url=(
            storage.get_url(animation.transcript_key)
            if animation.transcript_key
            else None
        ),
    )


def publish_animation(animation: Animation) -> None:
    """Flip `animation` to `published`. A transcript asset is mandatory — with
    none this raises `CannotPublish` and leaves the status untouched."""
    if not animation.transcript_key:
        raise CannotPublish(
            "an animation needs a transcript before it can be published"
        )
    animation.status = CONTENT_PUBLISHED
