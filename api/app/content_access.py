"""Shared content-visibility rule for the student-facing routers.

A Topic is visible to a student only once it carries a `published`
`LectureContent` row; a `ContentAdmin` additionally sees drafts. The content
router and the practice router both gate on this, so the rule lives here rather
than being reimplemented in each.
"""

from __future__ import annotations

from app.models import CONTENT_PUBLISHED, Topic


def topic_is_published(topic: Topic) -> bool:
    lc = topic.lecture_content
    return lc is not None and lc.status == CONTENT_PUBLISHED
