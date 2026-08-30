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

from typing import Literal

from app.models import CONTENT_DRAFT, CONTENT_PUBLISHED, Animation, Topic
from app.schemas import AnimationAdminOut, AnimationOut, TopicRef
from app.storage import MediaStorage

# The two asset kinds an animation carries, and, per kind, the extensions
# `media_key_for` will keep off an upload's filename plus the fallback it uses
# when the filename has none of them. `video_key` / `transcript_key` feed
# nginx's `/media/` location, which types the response by extension, so a
# stray extension must not ride through.
AssetKind = Literal["video", "transcript"]
_ASSET_EXTS: dict[AssetKind, tuple[frozenset[str], str]] = {
    "video": (frozenset({".mp4", ".webm", ".mov", ".m4v", ".ogv"}), ".mp4"),
    "transcript": (frozenset({".vtt", ".srt"}), ".vtt"),
}


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


def unpublish_animation(animation: Animation) -> None:
    """Pull `animation` back to `draft` — students stop seeing it, a
    `ContentAdmin` still does. Always allowed; the inverse of
    `publish_animation`."""
    animation.status = CONTENT_DRAFT


def media_key_for(slug: str, kind: AssetKind, filename: str | None) -> str:
    """The `MediaStorage` key an animation's `kind` asset is stored under.
    Derived from `slug` + `kind` so re-uploading the same kind overwrites in
    place; the extension is carried over from `filename` only when it is one
    this kind recognises, else the per-kind fallback."""
    allowed, fallback = _ASSET_EXTS[kind]
    ext = ""
    if filename and "." in filename:
        ext = "." + filename.rsplit(".", 1)[1].strip().lower()
    if ext not in allowed:
        ext = fallback
    return f"animations/{slug}/{kind}{ext}"


def admin_animation_out(
    animation: Animation, storage: MediaStorage
) -> AnimationAdminOut:
    """The ContentAdmin view of `animation`: exactly the student-facing view
    (`animation_out`) plus every Topic it is attached to, for the upload
    screen."""
    return AnimationAdminOut(
        **animation_out(animation, storage).model_dump(),
        topics=[TopicRef.model_validate(t) for t in animation.topics],
    )
