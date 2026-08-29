"""Content browsing and draft visibility, exercised through the HTTP API.

A small fixture tree is built directly in the DB (the real seed-ingest core is
ticket 05). Tests assert on responses and on the `TopicView` rows the lecture
endpoint writes — the observable behaviour, not internals.
"""

from __future__ import annotations

import pytest

from app.models import (
    CONTENT_DRAFT,
    CONTENT_PUBLISHED,
    ROLE_CONTENT_ADMIN,
    LectureContent,
    Subject,
    Topic,
    TopicView,
    Unit,
    User,
    YearLevel,
)
from tests.test_auth import login, register_and_verify


@pytest.fixture
def tree(db_session):
    """Year 7 → Mathematics with two Units. `Number` holds two published
    Topics (Fractions depends on Integers); `Algebra` holds a draft Topic and a
    published Topic whose only prerequisite is that draft."""
    y7 = YearLevel(name="Year 7", syllabus_region="AU-NSW")
    y8 = YearLevel(name="Year 8", syllabus_region="AU-NSW")
    db_session.add_all([y7, y8])
    db_session.flush()

    maths = Subject(year_level_id=y7.id, title="Mathematics", order=1)
    db_session.add(maths)
    db_session.flush()

    number = Unit(subject_id=maths.id, title="Number", order=1)
    algebra = Unit(subject_id=maths.id, title="Algebra", order=2)
    db_session.add_all([number, algebra])
    db_session.flush()

    integers = Topic(unit_id=number.id, title="Integers", slug="integers", order=1)
    fractions = Topic(unit_id=number.id, title="Fractions", slug="fractions", order=2)
    pronumerals = Topic(
        unit_id=algebra.id, title="Pronumerals", slug="pronumerals", order=1
    )
    equations = Topic(
        unit_id=algebra.id, title="Equations", slug="equations", order=2
    )
    db_session.add_all([integers, fractions, pronumerals, equations])
    db_session.flush()

    fractions.prerequisites.append(integers)
    equations.prerequisites.append(pronumerals)

    db_session.add_all(
        [
            LectureContent(
                topic_id=integers.id,
                body="# Integers\n\nA number line runs $-\\infty$ to $\\infty$.",
                status=CONTENT_PUBLISHED,
                version=1,
            ),
            LectureContent(
                topic_id=fractions.id,
                body="# Fractions\n\n$$\\frac{1}{2} + \\frac{1}{2} = 1$$",
                status=CONTENT_PUBLISHED,
                version=1,
            ),
            LectureContent(
                topic_id=pronumerals.id,
                body="# Pronumerals (draft)\n\nStill being written.",
                status=CONTENT_DRAFT,
                version=1,
            ),
            LectureContent(
                topic_id=equations.id,
                body="# Equations\n\nSolve for $x$.",
                status=CONTENT_PUBLISHED,
                version=1,
            ),
        ]
    )
    db_session.commit()

    return {
        "year7_id": y7.id,
        "year8_id": y8.id,
        "subject_id": maths.id,
        "number_id": number.id,
        "algebra_id": algebra.id,
    }


def _student(client, fake_email):
    creds = register_and_verify(client, fake_email)
    token = login(client, creds).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _content_admin(client, fake_email, db_session):
    creds = register_and_verify(
        client, fake_email, email="editor@example.com", name="Ed Itor"
    )
    user = db_session.query(User).filter_by(email="editor@example.com").one()
    user.role = ROLE_CONTENT_ADMIN
    db_session.commit()
    token = login(client, creds).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# -- tree listing ---------------------------------------------------------


def test_tree_lists_each_level_in_order(client, fake_email, tree):
    headers = _student(client, fake_email)

    years = client.get("/content/year-levels", headers=headers).json()
    assert [y["name"] for y in years] == ["Year 7", "Year 8"]
    assert years[0]["syllabus_region"] == "AU-NSW"

    subjects = client.get(
        f"/content/year-levels/{tree['year7_id']}/subjects", headers=headers
    ).json()
    assert [s["title"] for s in subjects] == ["Mathematics"]

    units = client.get(
        f"/content/subjects/{tree['subject_id']}/units", headers=headers
    ).json()
    assert [u["title"] for u in units] == ["Number", "Algebra"]  # by `order`

    topics = client.get(
        f"/content/units/{tree['number_id']}/topics", headers=headers
    ).json()
    assert [t["slug"] for t in topics] == ["integers", "fractions"]


def test_empty_year_level_returns_an_empty_subject_list(client, fake_email, tree):
    headers = _student(client, fake_email)
    resp = client.get(
        f"/content/year-levels/{tree['year8_id']}/subjects", headers=headers
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_unknown_parent_ids_are_404(client, fake_email, tree):
    headers = _student(client, fake_email)
    assert client.get("/content/year-levels/999/subjects", headers=headers).status_code == 404
    assert client.get("/content/subjects/999/units", headers=headers).status_code == 404
    assert client.get("/content/units/999/topics", headers=headers).status_code == 404


# -- draft visibility ---------------------------------------------------


def test_students_see_only_published_topics(client, fake_email, tree):
    headers = _student(client, fake_email)
    topics = client.get(
        f"/content/units/{tree['algebra_id']}/topics", headers=headers
    ).json()
    assert [t["slug"] for t in topics] == ["equations"]  # pronumerals is draft


def test_content_admin_sees_draft_topics(client, fake_email, db_session, tree):
    headers = _content_admin(client, fake_email, db_session)
    topics = client.get(
        f"/content/units/{tree['algebra_id']}/topics", headers=headers
    ).json()
    assert [t["slug"] for t in topics] == ["pronumerals", "equations"]


def test_student_cannot_open_a_draft_topic_but_an_admin_can(
    client, fake_email, db_session, tree
):
    student = _student(client, fake_email)
    assert client.get("/content/topics/pronumerals", headers=student).status_code == 404

    admin = _content_admin(client, fake_email, db_session)
    resp = client.get("/content/topics/pronumerals", headers=admin)
    assert resp.status_code == 200
    body = resp.json()
    assert body["lecture_content"]["status"] == "draft"
    assert "being written" in body["lecture_content"]["body"]


# -- topic detail -----------------------------------------------------


def test_topic_detail_carries_the_published_body_and_prereq_links(
    client, fake_email, tree
):
    headers = _student(client, fake_email)
    body = client.get("/content/topics/fractions", headers=headers).json()

    assert body["slug"] == "fractions"
    assert body["unit_id"] == tree["number_id"]
    assert body["lecture_content"]["status"] == "published"
    assert body["lecture_content"]["version"] == 1
    assert "\\frac{1}{2}" in body["lecture_content"]["body"]
    assert [p["slug"] for p in body["prerequisites"]] == ["integers"]


def test_prerequisites_that_are_drafts_are_hidden_from_students(
    client, fake_email, db_session, tree
):
    student = _student(client, fake_email)
    body = client.get("/content/topics/equations", headers=student).json()
    assert body["prerequisites"] == []  # its only prereq (pronumerals) is a draft

    admin = _content_admin(client, fake_email, db_session)
    admin_body = client.get("/content/topics/equations", headers=admin).json()
    assert [p["slug"] for p in admin_body["prerequisites"]] == ["pronumerals"]


def test_unknown_topic_slug_is_404(client, fake_email, tree):
    headers = _student(client, fake_email)
    assert client.get("/content/topics/nope", headers=headers).status_code == 404


# -- analytics: TopicView --------------------------------------------------


def test_opening_a_lecture_as_a_student_records_a_topic_view(
    client, fake_email, db_session, tree
):
    headers = _student(client, fake_email)
    student_id = db_session.query(User).filter_by(email="ada@example.com").one().id

    assert db_session.query(TopicView).count() == 0
    assert client.get("/content/topics/integers", headers=headers).status_code == 200

    views = db_session.query(TopicView).all()
    assert len(views) == 1
    assert views[0].user_id == student_id
    assert views[0].created_at is not None
    integers_id = db_session.query(Topic).filter_by(slug="integers").one().id
    assert views[0].topic_id == integers_id

    # Each open is its own event.
    client.get("/content/topics/integers", headers=headers)
    assert db_session.query(TopicView).count() == 2


def test_a_content_admin_preview_does_not_record_a_topic_view(
    client, fake_email, db_session, tree
):
    headers = _content_admin(client, fake_email, db_session)
    assert client.get("/content/topics/integers", headers=headers).status_code == 200
    assert db_session.query(TopicView).count() == 0


# -- auth gate ----------------------------------------------------------


def test_content_endpoints_require_authentication(client, tree):
    assert client.get("/content/year-levels").status_code == 401
    assert client.get("/content/topics/integers").status_code == 401
