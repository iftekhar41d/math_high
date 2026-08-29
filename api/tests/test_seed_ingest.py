"""Seed-ingest core: idempotency, validation, and the write-nothing guarantee.

The ingest has no HTTP endpoint in Phase 1 (it is the contract the future admin
upload UI will call), so these tests drive `app.ingest` directly with a small
fixture manifest and assert on persisted state. One test then confirms the
ingested tree serves through the content API, the way a student would see it.
"""

from __future__ import annotations

import pytest

from app.ingest import (
    ManifestError,
    ingest_manifest,
    load_and_ingest,
    parse_manifest,
)
from app.models import (
    LectureContent,
    Question,
    SkillTag,
    Subject,
    Topic,
    Unit,
    YearLevel,
)

# -- fixture manifest ---------------------------------------------------------

_LECTURES = {
    "lectures/integers.md": "# Integers\n\nA number line runs both ways.\n",
    "lectures/fractions.md": "# Fractions\n\n$$\\tfrac12 + \\tfrac12 = 1$$\n",
}


def _loader(ref: str) -> str:
    try:
        return _LECTURES[ref]
    except KeyError:  # pragma: no cover - guard for a mistyped fixture ref
        raise ManifestError(f"no such lecture file {ref!r}")


def _manifest() -> dict:
    """Year 7 → Mathematics → Number, with two Topics (Fractions requires
    Integers) and one question of each gradable type."""
    return {
        "year_levels": [
            {
                "slug": "year-7",
                "name": "Year 7",
                "syllabus_region": "AU-NSW",
                "subjects": [
                    {
                        "slug": "mathematics",
                        "title": "Mathematics",
                        "order": 1,
                        "units": [
                            {
                                "slug": "number",
                                "title": "Number",
                                "order": 1,
                                "topics": [
                                    {
                                        "slug": "integers",
                                        "title": "Integers",
                                        "order": 1,
                                        "lecture_file": "lectures/integers.md",
                                        "prerequisites": [],
                                        "questions": [
                                            {
                                                "slug": "int-add",
                                                "type": "mcq_single",
                                                "difficulty": "easy",
                                                "body": "What is $-3 + 5$?",
                                                "answer_schema": {
                                                    "options": [
                                                        {"id": "a", "text": "-8"},
                                                        {"id": "b", "text": "2"},
                                                        {"id": "c", "text": "8"},
                                                    ],
                                                    "correct_option": "b",
                                                },
                                                "worked_solution": "Count up 5 from -3.",
                                                "skill_tags": ["adding integers"],
                                            },
                                            {
                                                "slug": "int-negatives",
                                                "type": "mcq_multi",
                                                "difficulty": "medium",
                                                "body": "Which are negative?",
                                                "answer_schema": {
                                                    "options": [
                                                        {"id": "a", "text": "-4"},
                                                        {"id": "b", "text": "0"},
                                                        {"id": "c", "text": "-1"},
                                                    ],
                                                    "correct_options": ["a", "c"],
                                                },
                                                "worked_solution": "Less than zero.",
                                                "skill_tags": ["ordering integers"],
                                            },
                                        ],
                                    },
                                    {
                                        "slug": "fractions",
                                        "title": "Fractions",
                                        "order": 2,
                                        "lecture_file": "lectures/fractions.md",
                                        "prerequisites": ["integers"],
                                        "questions": [
                                            {
                                                "slug": "frac-divide",
                                                "type": "numeric",
                                                "difficulty": "hard",
                                                "body": "Evaluate $12 \\div 7$ (2 dp).",
                                                "answer_schema": {
                                                    "value": 1.71,
                                                    "tolerance": 0.01,
                                                },
                                                "worked_solution": "1.714... → 1.71.",
                                                "skill_tags": ["adding integers"],
                                            }
                                        ],
                                    },
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }


def _counts(db) -> dict[str, int]:
    return {
        "year_levels": db.query(YearLevel).count(),
        "subjects": db.query(Subject).count(),
        "units": db.query(Unit).count(),
        "topics": db.query(Topic).count(),
        "lectures": db.query(LectureContent).count(),
        "questions": db.query(Question).count(),
        "skill_tags": db.query(SkillTag).count(),
    }


def _ingest(db, data: dict | None = None):
    if data is None:
        data = _manifest()
    return ingest_manifest(db, parse_manifest(data, lecture_loader=_loader))


# -- idempotency ------------------------------------------------------------


def test_ingest_creates_the_whole_tree(db_session):
    summary = _ingest(db_session)

    assert _counts(db_session) == {
        "year_levels": 1,
        "subjects": 1,
        "units": 1,
        "topics": 2,
        "lectures": 2,
        "questions": 3,
        "skill_tags": 2,  # "adding integers" is shared by two questions
    }
    assert summary.as_dict() == {
        "year_levels": 1,
        "subjects": 1,
        "units": 1,
        "topics": 2,
        "questions": 3,
        "skill_tags": 2,
    }

    fractions = db_session.query(Topic).filter_by(slug="fractions").one()
    assert [p.slug for p in fractions.prerequisites] == ["integers"]
    assert fractions.lecture_content.status == "published"
    assert fractions.lecture_content.version == 1


def test_running_twice_yields_exactly_one_set_of_rows(db_session):
    _ingest(db_session)
    first = _counts(db_session)
    integers_id = db_session.query(Topic).filter_by(slug="integers").one().id

    _ingest(db_session)  # same input, again

    assert _counts(db_session) == first
    # Same rows, not replacements.
    assert db_session.query(Topic).filter_by(slug="integers").one().id == integers_id
    fractions = db_session.query(Topic).filter_by(slug="fractions").one()
    assert [p.slug for p in fractions.prerequisites] == ["integers"]
    assert fractions.lecture_content.version == 1  # unchanged body → no bump


def test_second_run_updates_changed_fields_in_place(db_session):
    _ingest(db_session)
    q_id = db_session.query(Question).filter_by(slug="int-add").one().id

    data = _manifest()
    unit = data["year_levels"][0]["subjects"][0]["units"][0]
    unit["title"] = "Number and Integers"
    integers = unit["topics"][0]
    integers["questions"][0]["body"] = "What is $-3 + 6$?"
    _LECTURES["lectures/integers.md"] = "# Integers\n\nNow with more detail.\n"
    try:
        _ingest(db_session, data)
    finally:
        _LECTURES["lectures/integers.md"] = "# Integers\n\nA number line runs both ways.\n"

    assert db_session.query(Unit).one().title == "Number and Integers"
    q = db_session.query(Question).filter_by(slug="int-add").one()
    assert q.id == q_id  # updated, not re-inserted
    assert q.body == "What is $-3 + 6$?"
    integers_topic = db_session.query(Topic).filter_by(slug="integers").one()
    assert "more detail" in integers_topic.lecture_content.body
    assert integers_topic.lecture_content.version == 2  # body changed → bumped

    assert _counts(db_session)["questions"] == 3  # still three


def test_content_dropped_from_the_manifest_is_left_in_place(db_session):
    _ingest(db_session)

    data = _manifest()
    topics = data["year_levels"][0]["subjects"][0]["units"][0]["topics"]
    topics[0]["questions"] = topics[0]["questions"][:1]  # drop int-negatives
    _ingest(db_session, data)

    # Not pruned — it may already carry attempt rows.
    assert db_session.query(Question).filter_by(slug="int-negatives").count() == 1


# -- malformed manifests: clear error, nothing written --------------------


def _assert_nothing_written(db):
    assert _counts(db) == {k: 0 for k in _counts(db)}


@pytest.mark.parametrize(
    "mutate, needle",
    [
        pytest.param(
            lambda d: _set_question_field(d, "type", "true_false"),
            "unknown question type",
            id="unknown-question-type",
        ),
        pytest.param(
            lambda d: _set_question_field(d, "difficulty", "trivial"),
            "unknown difficulty",
            id="unknown-difficulty",
        ),
        pytest.param(
            lambda d: _drop_question_field(d, "worked_solution"),
            "worked_solution",
            id="missing-required-field",
        ),
        pytest.param(
            lambda d: _set_prereq(d, ["algebra"]),
            "not a topic in this manifest",
            id="bad-prerequisite-reference",
        ),
        pytest.param(
            lambda d: _set_prereq(d, ["fractions"]),  # topic 2 requiring itself
            "lists itself as a prerequisite",
            id="self-prerequisite",
        ),
        pytest.param(
            lambda d: _dup_topic_slug(d),
            "used more than once",
            id="duplicate-slug",
        ),
        pytest.param(
            lambda d: _break_mcq_answer(d),
            "not one of the option ids",
            id="answer-schema-does-not-grade",
        ),
        pytest.param(
            lambda d: d.pop("year_levels"),
            "year_levels",
            id="missing-top-level-key",
        ),
    ],
)
def test_malformed_manifest_is_rejected_and_writes_nothing(db_session, mutate, needle):
    data = _manifest()
    mutate(data)

    with pytest.raises(ManifestError) as excinfo:
        _ingest(db_session, data)

    assert needle in str(excinfo.value)
    _assert_nothing_written(db_session)


def test_a_non_mapping_root_is_rejected(db_session):
    with pytest.raises(ManifestError, match="mapping"):
        parse_manifest([{"slug": "x"}], lecture_loader=_loader)
    _assert_nothing_written(db_session)


# -- helpers for the parametrized mutations ------------------------------


def _first_question(d: dict) -> dict:
    return d["year_levels"][0]["subjects"][0]["units"][0]["topics"][0]["questions"][0]


def _set_question_field(d: dict, key: str, value) -> None:
    _first_question(d)[key] = value


def _drop_question_field(d: dict, key: str) -> None:
    _first_question(d).pop(key)


def _set_prereq(d: dict, prereqs: list[str]) -> None:
    d["year_levels"][0]["subjects"][0]["units"][0]["topics"][1]["prerequisites"] = prereqs


def _dup_topic_slug(d: dict) -> None:
    d["year_levels"][0]["subjects"][0]["units"][0]["topics"][1]["slug"] = "integers"


def _break_mcq_answer(d: dict) -> None:
    _first_question(d)["answer_schema"]["correct_option"] = "z"


# -- file loading (load_manifest_file) ----------------------------------


def _write_fixture(tmp_path):
    (tmp_path / "lectures").mkdir()
    (tmp_path / "lectures" / "integers.md").write_text("# Integers\n\nBody.\n")
    (tmp_path / "lectures" / "fractions.md").write_text("# Fractions\n\nBody.\n")
    import yaml

    (tmp_path / "manifest.yaml").write_text(yaml.safe_dump(_manifest()))
    return tmp_path / "manifest.yaml"


def test_load_and_ingest_reads_yaml_and_sibling_lecture_files(db_session, tmp_path):
    summary = load_and_ingest(db_session, _write_fixture(tmp_path))

    assert summary.topics == 2
    integers = db_session.query(Topic).filter_by(slug="integers").one()
    assert "Body." in integers.lecture_content.body


def test_missing_lecture_file_is_rejected(db_session, tmp_path):
    path = _write_fixture(tmp_path)
    (tmp_path / "lectures" / "fractions.md").unlink()

    with pytest.raises(ManifestError, match="cannot read lecture file"):
        load_and_ingest(db_session, path)
    _assert_nothing_written(db_session)


def test_invalid_yaml_is_rejected(db_session, tmp_path):
    (tmp_path / "manifest.yaml").write_text("year_levels: [ unclosed\n")
    with pytest.raises(ManifestError, match="not valid YAML"):
        load_and_ingest(db_session, tmp_path / "manifest.yaml")


def test_missing_manifest_file_is_rejected(db_session, tmp_path):
    with pytest.raises(ManifestError, match="cannot read manifest"):
        load_and_ingest(db_session, tmp_path / "nope.yaml")


# -- end to end: ingested content serves through the API ----------------


def test_ingested_tree_is_browsable_through_the_content_api(
    client, db_session, fake_email
):
    from tests.test_auth import login, register_and_verify

    _ingest(db_session)

    creds = register_and_verify(client, fake_email)
    token = login(client, creds).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    years = client.get("/content/year-levels", headers=headers).json()
    assert [y["name"] for y in years] == ["Year 7"]

    subjects = client.get(
        f"/content/year-levels/{years[0]['id']}/subjects", headers=headers
    ).json()
    assert [s["title"] for s in subjects] == ["Mathematics"]

    detail = client.get("/content/topics/fractions", headers=headers).json()
    assert detail["lecture_content"]["status"] == "published"
    assert [p["slug"] for p in detail["prerequisites"]] == ["integers"]

    session = client.post(
        "/practice/sessions", json={"topic_slug": "integers"}, headers=headers
    ).json()
    assert [q["type"] for q in session["questions"]] == ["mcq_single", "mcq_multi"]
    # The chokepoint still holds for ingested questions.
    assert "correct_option" not in client.post(
        "/practice/sessions", json={"topic_slug": "integers"}, headers=headers
    ).text
