"""Animations: the many-to-many model, the publish gate, and the student
surface on the Topic-detail response.

The animation rows are seeded directly in the DB (the ContentAdmin upload
screen is ticket 11). Tests assert on the `GET /content/topics/{slug}`
response — published-only for a student, drafts too for a `ContentAdmin` — and
on `publish_animation`, the shared rule that a transcript is required to publish.
"""

from __future__ import annotations

import pytest

from app.animations import CannotPublish, publish_animation
from app.models import (
    CONTENT_DRAFT,
    CONTENT_PUBLISHED,
    Animation,
    LectureContent,
    Subject,
    Topic,
    Unit,
    YearLevel,
)
from tests.test_content import _content_admin, _student


@pytest.fixture
def anim_tree(db_session):
    """Year 7 → Mathematics → Number with two published Topics, "Integers" and
    "Fractions"."""
    y7 = YearLevel(name="Year 7", syllabus_region="AU-NSW")
    db_session.add(y7)
    db_session.flush()
    maths = Subject(year_level_id=y7.id, title="Mathematics", order=1)
    db_session.add(maths)
    db_session.flush()
    number = Unit(subject_id=maths.id, title="Number", order=1)
    db_session.add(number)
    db_session.flush()

    integers = Topic(
        unit_id=number.id, title="Integers", slug="integers", order=1
    )
    fractions = Topic(
        unit_id=number.id, title="Fractions", slug="fractions", order=2
    )
    db_session.add_all([integers, fractions])
    db_session.flush()
    db_session.add_all(
        [
            LectureContent(
                topic_id=integers.id,
                body="# Integers",
                status=CONTENT_PUBLISHED,
                version=1,
            ),
            LectureContent(
                topic_id=fractions.id,
                body="# Fractions",
                status=CONTENT_PUBLISHED,
                version=1,
            ),
        ]
    )
    db_session.commit()
    return {"integers_id": integers.id, "fractions_id": fractions.id}


def _add_animation(db_session, *, slug, topic_ids, status, transcript=True):
    anim = Animation(
        slug=slug,
        title=f"{slug} explained",
        description=f"A short visual walk-through of {slug}.",
        video_key=f"animations/{slug}.mp4",
        transcript_key=f"animations/{slug}.vtt" if transcript else None,
        duration_seconds=42,
        status=status,
    )
    for tid in topic_ids:
        anim.topics.append(db_session.get(Topic, tid))
    db_session.add(anim)
    db_session.commit()
    return anim


# -- many-to-many attachment ---------------------------------------------


def test_one_animation_attaches_to_two_topics(
    client, fake_email, anim_tree, db_session
):
    _add_animation(
        db_session,
        slug="number-line",
        topic_ids=[anim_tree["integers_id"], anim_tree["fractions_id"]],
        status=CONTENT_PUBLISHED,
    )
    headers = _student(client, fake_email)

    for slug in ("integers", "fractions"):
        body = client.get(f"/content/topics/{slug}", headers=headers).json()
        assert [a["slug"] for a in body["animations"]] == ["number-line"]


def test_two_animations_on_one_topic_are_listed_in_creation_order(
    client, fake_email, anim_tree, db_session
):
    _add_animation(
        db_session,
        slug="first",
        topic_ids=[anim_tree["integers_id"]],
        status=CONTENT_PUBLISHED,
    )
    _add_animation(
        db_session,
        slug="second",
        topic_ids=[anim_tree["integers_id"]],
        status=CONTENT_PUBLISHED,
    )
    headers = _student(client, fake_email)

    body = client.get("/content/topics/integers", headers=headers).json()
    assert [a["slug"] for a in body["animations"]] == ["first", "second"]


def test_a_topic_with_no_animations_returns_an_empty_list(
    client, fake_email, anim_tree
):
    headers = _student(client, fake_email)
    body = client.get("/content/topics/fractions", headers=headers).json()
    assert body["animations"] == []


# -- draft / published visibility --------------------------------------


def test_students_see_only_published_animations(
    client, fake_email, anim_tree, db_session
):
    _add_animation(
        db_session,
        slug="published-one",
        topic_ids=[anim_tree["integers_id"]],
        status=CONTENT_PUBLISHED,
    )
    _add_animation(
        db_session,
        slug="draft-one",
        topic_ids=[anim_tree["integers_id"]],
        status=CONTENT_DRAFT,
    )
    headers = _student(client, fake_email)

    body = client.get("/content/topics/integers", headers=headers).json()
    anims = body["animations"]
    assert [a["slug"] for a in anims] == ["published-one"]
    only = anims[0]
    assert only["status"] == "published"
    assert only["video_url"] == "/media/animations/published-one.mp4"
    assert only["transcript_url"] == "/media/animations/published-one.vtt"
    assert only["duration_seconds"] == 42


def test_content_admin_also_sees_draft_animations(
    client, fake_email, db_session, anim_tree
):
    _add_animation(
        db_session,
        slug="published-one",
        topic_ids=[anim_tree["integers_id"]],
        status=CONTENT_PUBLISHED,
    )
    _add_animation(
        db_session,
        slug="draft-no-transcript",
        topic_ids=[anim_tree["integers_id"]],
        status=CONTENT_DRAFT,
        transcript=False,
    )
    headers = _content_admin(client, fake_email, db_session)

    body = client.get("/content/topics/integers", headers=headers).json()
    by_slug = {a["slug"]: a for a in body["animations"]}
    assert set(by_slug) == {"published-one", "draft-no-transcript"}
    assert by_slug["draft-no-transcript"]["status"] == "draft"
    # No transcript uploaded yet -> null, not a bogus URL.
    assert by_slug["draft-no-transcript"]["transcript_url"] is None


# -- the publish gate --------------------------------------------------


def test_publish_is_blocked_without_a_transcript(db_session, anim_tree):
    anim = _add_animation(
        db_session,
        slug="needs-transcript",
        topic_ids=[anim_tree["integers_id"]],
        status=CONTENT_DRAFT,
        transcript=False,
    )

    with pytest.raises(CannotPublish):
        publish_animation(anim)
    assert anim.status == CONTENT_DRAFT

    # Attach a transcript and it publishes.
    anim.transcript_key = "animations/needs-transcript.vtt"
    publish_animation(anim)
    assert anim.status == CONTENT_PUBLISHED
