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

from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingest.manifest import (
    Manifest,
    QuestionSpec,
    SubjectSpec,
    TopicSpec,
    UnitSpec,
    YearLevelSpec,
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


@dataclass
class IngestSummary:
    """How many rows of each kind the run touched (created or updated)."""

    year_levels: int = 0
    subjects: int = 0
    units: int = 0
    topics: int = 0
    questions: int = 0
    skill_tags: int = 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


def ingest_manifest(db: Session, manifest: Manifest) -> IngestSummary:
    """Upsert everything in `manifest`. Commits on success; on any error rolls
    back so a failed run writes nothing."""
    summary = IngestSummary()
    tag_cache: dict[str, SkillTag] = {}
    topics_by_slug: dict[str, Topic] = {}
    try:
        for yl_spec in manifest.year_levels:
            year_level = _upsert_year_level(db, yl_spec)
            summary.year_levels += 1
            for subj_spec in yl_spec.subjects:
                subject = _upsert_subject(db, year_level, subj_spec)
                summary.subjects += 1
                for unit_spec in subj_spec.units:
                    unit = _upsert_unit(db, subject, unit_spec)
                    summary.units += 1
                    for topic_spec in unit_spec.topics:
                        topic = _upsert_topic(db, unit, topic_spec)
                        topics_by_slug[topic_spec.slug] = topic
                        summary.topics += 1
                        _upsert_lecture(db, topic, topic_spec)
                        for q_spec in topic_spec.questions:
                            _upsert_question(db, topic, q_spec, tag_cache)
                            summary.questions += 1
        db.flush()

        # Second pass: wire prerequisites now that every Topic row exists.
        for _unit, topic_spec in manifest.iter_topics():
            topic = topics_by_slug[topic_spec.slug]
            topic.prerequisites = [
                topics_by_slug[slug] for slug in topic_spec.prerequisites
            ]

        summary.skill_tags = len(tag_cache)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return summary


def load_and_ingest(db: Session, manifest_path: str | Path) -> IngestSummary:
    """Read + validate the manifest at `manifest_path`, then ingest it."""
    return ingest_manifest(db, load_manifest_file(manifest_path))


def _upsert_year_level(db: Session, spec: YearLevelSpec) -> YearLevel:
    row = db.scalar(select(YearLevel).where(YearLevel.slug == spec.slug))
    if row is None:
        row = YearLevel(slug=spec.slug)
        db.add(row)
    row.name = spec.name
    row.syllabus_region = spec.syllabus_region
    db.flush()
    return row


def _upsert_subject(
    db: Session, year_level: YearLevel, spec: SubjectSpec
) -> Subject:
    row = db.scalar(select(Subject).where(Subject.slug == spec.slug))
    if row is None:
        row = Subject(slug=spec.slug)
        db.add(row)
    row.year_level_id = year_level.id
    row.title = spec.title
    row.order = spec.order
    db.flush()
    return row


def _upsert_unit(db: Session, subject: Subject, spec: UnitSpec) -> Unit:
    row = db.scalar(select(Unit).where(Unit.slug == spec.slug))
    if row is None:
        row = Unit(slug=spec.slug)
        db.add(row)
    row.subject_id = subject.id
    row.title = spec.title
    row.order = spec.order
    db.flush()
    return row


def _upsert_topic(db: Session, unit: Unit, spec: TopicSpec) -> Topic:
    row = db.scalar(select(Topic).where(Topic.slug == spec.slug))
    if row is None:
        row = Topic(slug=spec.slug)
        db.add(row)
    row.unit_id = unit.id
    row.title = spec.title
    row.order = spec.order
    db.flush()
    return row


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
) -> None:
    row = db.scalar(select(Question).where(Question.slug == spec.slug))
    if row is None:
        row = Question(slug=spec.slug)
        db.add(row)
    row.topic_id = topic.id
    row.type = spec.type
    row.difficulty = spec.difficulty
    row.body = spec.body
    row.answer_schema = spec.answer_schema
    row.worked_solution = spec.worked_solution
    row.skill_tags = [_get_tag(db, name, tag_cache) for name in spec.skill_tags]
    db.flush()


def _get_tag(
    db: Session, name: str, cache: dict[str, SkillTag]
) -> SkillTag:
    if name in cache:
        return cache[name]
    tag = db.scalar(select(SkillTag).where(SkillTag.name == name))
    if tag is None:
        tag = SkillTag(name=name)
        db.add(tag)
        db.flush()
    cache[name] = tag
    return tag
