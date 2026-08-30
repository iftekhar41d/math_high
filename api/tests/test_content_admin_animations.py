"""`/content-admin/animations` — the ContentAdmin animation upload/attach/publish
API (Phase 2 ticket 11).

Tests drive the real HTTP surface: a multipart upload creates a draft
`Animation` with its assets stored through the media seam; the row attaches to
one or more Topics; publishing needs a transcript; and only a `ContentAdmin`
reaches any of it.
"""

from __future__ import annotations

from app.models import ROLE_SUPER_ADMIN, User
from tests.test_auth import login, register_and_verify
from tests.test_content import _content_admin, _student

VIDEO = ("number-line.mp4", b"fake-mp4-bytes", "video/mp4")
TRANSCRIPT = ("number-line.vtt", b"WEBVTT\n\n00:00.000 --> 00:02.000\nHi", "text/vtt")


def _super_admin(client, fake_email, db_session):
    creds = register_and_verify(
        client, fake_email, email="root@example.com", name="Sue Peruser"
    )
    user = db_session.query(User).filter_by(email="root@example.com").one()
    user.role = ROLE_SUPER_ADMIN
    db_session.commit()
    token = login(client, creds).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _tree(db_session):
    """Year 7 → Mathematics → Number with two Topics."""
    from app.models import Subject, Topic, Unit, YearLevel

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
    db_session.commit()
    return {"integers": integers.id, "fractions": fractions.id}


def _upload(client, headers, *, slug="number-line", transcript=False, **fields):
    files = {"video": VIDEO}
    if transcript:
        files["transcript"] = TRANSCRIPT
    data = {"slug": slug, "title": f"{slug} explained", **fields}
    return client.post(
        "/content-admin/animations", data=data, files=files, headers=headers
    )


# -- upload -> draft animation with stored assets ----------------------------


def test_upload_creates_a_draft_animation_with_stored_assets(
    client, fake_email, db_session, fake_media
):
    headers = _content_admin(client, fake_email, db_session)

    resp = _upload(
        client,
        headers,
        transcript=True,
        description="A visual walk-through.",
        duration_seconds=42,
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["slug"] == "number-line"
    assert body["status"] == "draft"
    assert body["description"] == "A visual walk-through."
    assert body["duration_seconds"] == 42
    assert body["video_url"] == "/media/animations/number-line/video.mp4"
    assert body["transcript_url"] == "/media/animations/number-line/transcript.vtt"
    assert body["topics"] == []

    # The bytes actually went through the media seam.
    assert fake_media.saved["animations/number-line/video.mp4"] == VIDEO[1]
    assert fake_media.saved["animations/number-line/transcript.vtt"] == TRANSCRIPT[1]


def test_upload_without_a_transcript_leaves_transcript_url_null(
    client, fake_email, db_session
):
    headers = _content_admin(client, fake_email, db_session)
    body = _upload(client, headers).json()
    assert body["transcript_url"] is None
    assert body["status"] == "draft"


def test_re_uploading_the_same_slug_updates_in_place(
    client, fake_email, db_session
):
    headers = _content_admin(client, fake_email, db_session)
    first = _upload(client, headers, title="draft title").json()

    resp = client.post(
        "/content-admin/animations",
        data={"slug": "number-line", "title": "final title"},
        files={"transcript": TRANSCRIPT},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == first["id"]
    assert body["title"] == "final title"
    # Video from the first upload is retained; transcript is now set.
    assert body["video_url"] == "/media/animations/number-line/video.mp4"
    assert body["transcript_url"] == "/media/animations/number-line/transcript.vtt"


def test_a_new_animation_needs_a_video(client, fake_email, db_session):
    headers = _content_admin(client, fake_email, db_session)
    resp = client.post(
        "/content-admin/animations",
        data={"slug": "no-video", "title": "No video"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_a_malformed_slug_is_rejected(client, fake_email, db_session):
    headers = _content_admin(client, fake_email, db_session)
    resp = client.post(
        "/content-admin/animations",
        data={"slug": "../etc/passwd", "title": "Nope"},
        files={"video": VIDEO},
        headers=headers,
    )
    assert resp.status_code == 422


def test_an_unrecognised_video_extension_falls_back_to_mp4(
    client, fake_email, db_session, fake_media
):
    headers = _content_admin(client, fake_email, db_session)
    resp = client.post(
        "/content-admin/animations",
        data={"slug": "odd-ext", "title": "Odd"},
        files={"video": ("clip.bin", b"bytes", "application/octet-stream")},
        headers=headers,
    )
    assert resp.json()["video_url"] == "/media/animations/odd-ext/video.mp4"
    assert "animations/odd-ext/video.mp4" in fake_media.saved


# -- attach / detach Topics -----------------------------------------------


def test_attach_to_multiple_topics_then_detach_one(
    client, fake_email, db_session
):
    headers = _content_admin(client, fake_email, db_session)
    ids = _tree(db_session)
    _upload(client, headers, transcript=True)

    resp = client.put(
        "/content-admin/animations/number-line/topics",
        json={"topic_ids": [ids["integers"], ids["fractions"]]},
        headers=headers,
    )
    assert resp.status_code == 200
    assert {t["slug"] for t in resp.json()["topics"]} == {
        "integers",
        "fractions",
    }

    # Replace the set with just one -> the other is detached.
    resp = client.put(
        "/content-admin/animations/number-line/topics",
        json={"topic_ids": [ids["fractions"]]},
        headers=headers,
    )
    assert [t["slug"] for t in resp.json()["topics"]] == ["fractions"]


def test_attach_to_an_unknown_topic_is_404(client, fake_email, db_session):
    headers = _content_admin(client, fake_email, db_session)
    _upload(client, headers)
    resp = client.put(
        "/content-admin/animations/number-line/topics",
        json={"topic_ids": [9999]},
        headers=headers,
    )
    assert resp.status_code == 404


# -- publish / unpublish -------------------------------------------------


def test_publish_then_a_student_sees_it_on_the_topic(
    client, fake_email, db_session
):
    headers = _content_admin(client, fake_email, db_session)
    ids = _tree(db_session)
    from app.models import CONTENT_PUBLISHED, LectureContent

    db_session.add(
        LectureContent(
            topic_id=ids["integers"], body="# Integers",
            status=CONTENT_PUBLISHED, version=1,
        )
    )
    db_session.commit()

    _upload(client, headers, transcript=True)
    client.put(
        "/content-admin/animations/number-line/topics",
        json={"topic_ids": [ids["integers"]]},
        headers=headers,
    )

    resp = client.post(
        "/content-admin/animations/number-line/publish", headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "published"

    student = _student(client, fake_email)
    topic = client.get("/content/topics/integers", headers=student).json()
    assert [a["slug"] for a in topic["animations"]] == ["number-line"]

    # And it can be pulled back to draft.
    resp = client.post(
        "/content-admin/animations/number-line/unpublish", headers=headers
    )
    assert resp.json()["status"] == "draft"
    topic = client.get("/content/topics/integers", headers=student).json()
    assert topic["animations"] == []


def test_publish_is_refused_without_a_transcript(
    client, fake_email, db_session
):
    headers = _content_admin(client, fake_email, db_session)
    _upload(client, headers)  # no transcript

    resp = client.post(
        "/content-admin/animations/number-line/publish", headers=headers
    )
    assert resp.status_code == 409
    assert (
        client.get(
            "/content-admin/animations/number-line", headers=headers
        ).json()["status"]
        == "draft"
    )


# -- access control ----------------------------------------------------


def test_a_student_is_refused_everywhere(client, fake_email, db_session):
    admin = _content_admin(client, fake_email, db_session)
    _upload(client, admin, transcript=True)
    student = _student(client, fake_email)

    assert client.get("/content-admin/animations", headers=student).status_code == 403
    assert (
        client.post(
            "/content-admin/animations",
            data={"slug": "x", "title": "x"},
            files={"video": VIDEO},
            headers=student,
        ).status_code
        == 403
    )
    assert (
        client.put(
            "/content-admin/animations/number-line/topics",
            json={"topic_ids": []},
            headers=student,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/content-admin/animations/number-line/publish", headers=student
        ).status_code
        == 403
    )


def test_a_super_admin_is_also_refused(client, fake_email, db_session):
    root = _super_admin(client, fake_email, db_session)
    assert client.get("/content-admin/animations", headers=root).status_code == 403


def test_an_anonymous_caller_is_401(client):
    assert client.get("/content-admin/animations").status_code == 401


# -- the Topic picker feed --------------------------------------------------


def test_topics_feed_lists_every_topic_with_its_context(
    client, fake_email, db_session
):
    headers = _content_admin(client, fake_email, db_session)
    _tree(db_session)
    rows = client.get("/content-admin/topics", headers=headers).json()
    assert [r["slug"] for r in rows] == ["integers", "fractions"]
    assert rows[0]["unit_title"] == "Number"
    assert rows[0]["subject_title"] == "Mathematics"
    assert rows[0]["year_level_name"] == "Year 7"


def test_topics_feed_is_content_admin_only(client, fake_email, db_session):
    student = _student(client, fake_email)
    assert client.get("/content-admin/topics", headers=student).status_code == 403
