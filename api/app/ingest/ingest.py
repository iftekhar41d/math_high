"""Upsert a validated `Manifest` into the database, by slug.

`ingest_manifest(db, manifest)` is the reusable core: it matches every entity
by its `slug`, updates it in place if it exists and inserts it otherwise, and
does the whole run in one transaction. Running it a second time over the same
manifest changes nothing and creates nothing — the acceptance test for the
seed command.

Entities dropped from the manifest between runs are **left alone**, not
deleted: a `Topic` or `Question` may already have `QuestionAttempt` /
`TopicView` rows hanging off it, and content authoring must never destroy
student data. Removing content is a deliberate, separate operation.

A future admin upload UI calls `parse_manifest` then this function directly;
the CLI (`python -m app.ingest`) is only a wrapper.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import Base
from app.ingest.manifest import (
    Manifest,
    QuestionSpec,
    TopicSpec,
    assert_manifest_consistent,
    load_manifest_file,
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

# The kinds a summary reports, in tree order.
_KINDS = ("year_levels", "subjects", "units", "topics", "questions", "skill_tags")


@dataclass
class IngestSummary:
    """Per kind: how many rows the manifest covers (`total`) and how many of
    those the run actually inserted (`created`). A no-op re-run has every
    `created` at zero."""

    total: dict[str, int] = field(
        default_factory=lambda: {k: 0 for k in _KINDS}
    )
    created: dict[str, int] = field(
        default_factory=lambda: {k: 0 for k in _KINDS}
    )

    def record(self, kind: str, was_created: bool) -> None:
        self.total[kind] += 1
        if was_created:
            self.created[kind] += 1


def ingest_manifest(db: Session, manifest: Manifest) -> IngestSummary:
    """Upsert everything in `manifest`. Re-validates cross-entity consistency
    first (so a hand-built `Manifest` is held to the same guarantees as a parsed
    one), commits on success, and on any error rolls back so a failed run writes
    nothing."""
    assert_manifest_consistent(manifest)

    summary = IngestSummary()
    tag_cache: dict[str, SkillTag] = {}
    topics_by_slug: dict[str, Topic] = {}
    try:
        for yl_spec in manifest.year_levels:
            year_level, made = _upsert_by_slug(db, YearLevel, yl_spec.slug)
            year_level.name = yl_spec.name
            year_level.syllabus_region = yl_spec.syllabus_region
            db.flush()
            summary.record("year_levels", made)

            for subj_spec in yl_spec.subjects:
                subject, made = _upsert_by_slug(db, Subject, subj_spec.slug)
                subject.year_level_id = year_level.id
                subject.title = subj_spec.title
                subject.order = subj_spec.order
                db.flush()
                summary.record("subjects", made)

                for unit_spec in subj_spec.units:
                    unit, made = _upsert_by_slug(db, Unit, unit_spec.slug)
                    unit.subject_id = subject.id
                    unit.title = unit_spec.title
                    unit.order = unit_spec.order
                    db.flush()
                    summary.record("units", made)

                    for topic_spec in unit_spec.topics:
                        topic, made = _upsert_by_slug(db, Topic, topic_spec.slug)
                        topic.unit_id = unit.id
                        topic.title = topic_spec.title
                        topic.order = topic_spec.order
                        db.flush()
                        topics_by_slug[topic_spec.slug] = topic
                        summary.record("topics", made)

                        _upsert_lecture(db, topic, topic_spec)
                        for q_spec in topic_spec.questions:
                            made = _upsert_question(
                                db, topic, q_spec, tag_cache, summary
                            )
                            summary.record("questions", made)
        db.flush()

        # Second pass: wire prerequisites now that every Topic row exists.
        for topic_spec in manifest.iter_topics():
            topic = topics_by_slug[topic_spec.slug]
            topic.prerequisites = [
                topics_by_slug[slug] for slug in topic_spec.prerequisites
            ]

        db.commit()
    except Exception:
        db.rollback()
        raise
    return summary


def load_and_ingest(db: Session, manifest_path: str | Path) -> IngestSummary:
    """Read + validate the manifest at `manifest_path`, then ingest it."""
    return ingest_manifest(db, load_manifest_file(manifest_path))


def _upsert_by_slug(
    db: Session, model: type[Base], slug: str
) -> tuple[Base, bool]:
    """Return `(row, created)` for the `model` row with this `slug`, inserting a
    bare one if absent. The caller sets the remaining columns."""
    row = db.scalar(select(model).where(model.slug == slug))
    if row is not None:
        return row, False
    row = model(slug=slug)
    db.add(row)
    return row, True


def _upsert_lecture(db: Session, topic: Topic, spec: TopicSpec) -> None:
    lecture = topic.lecture_content
    if lecture is None:
        lecture = LectureContent(
            topic_id=topic.id,
            body=spec.lecture_body,
            status=spec.status,
            version=1,
        )
        topic.lecture_content = lecture
        db.add(lecture)
    else:
        # Bump the version only when the body genuinely changed, so a re-run
        # over unchanged content leaves the row byte-for-byte identical.
        if lecture.body != spec.lecture_body:
            lecture.version = (lecture.version or 1) + 1
        lecture.body = spec.lecture_body
        lecture.status = spec.status
    db.flush()


def _upsert_question(
    db: Session,
    topic: Topic,
    spec: QuestionSpec,
    tag_cache: dict[str, SkillTag],
    summary: IngestSummary,
) -> bool:
    row, created = _upsert_by_slug(db, Question, spec.slug)
    row.topic_id = topic.id
    row.type = spec.type
    row.difficulty = spec.difficulty
    row.body = spec.body
    row.answer_schema = spec.answer_schema
    row.worked_solution = spec.worked_solution
    row.skill_tags = [
        _get_tag(db, name, tag_cache, summary) for name in spec.skill_tags
    ]
    db.flush()
    return created


def _get_tag(
    db: Session,
    name: str,
    cache: dict[str, SkillTag],
    summary: IngestSummary,
) -> SkillTag:
    if name in cache:
        return cache[name]
    tag = db.scalar(select(SkillTag).where(SkillTag.name == name))
    if tag is None:
        tag = SkillTag(name=name)
        db.add(tag)
        db.flush()
        summary.record("skill_tags", True)
    else:
        summary.record("skill_tags", False)
    cache[name] = tag
    return tag
