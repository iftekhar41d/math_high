"""Parse and validate a course manifest — the format a content admin authors.

The manifest is a YAML (or JSON — same shape) document describing the whole
tree:

```yaml
year_levels:
  - slug: year-7
    name: "Year 7"
    syllabus_region: AU-NSW
    subjects:
      - slug: mathematics
        title: Mathematics
        order: 1
        units:
          - slug: computation-with-integers
            title: "Computation with Integers"
            order: 1
            topics:
              - slug: integers-and-the-number-line
                title: "Integers and the Number Line"
                order: 1
                status: published            # or "draft"; default published
                lecture_file: lectures/integers-and-the-number-line.md
                prerequisites: []            # list of topic slugs
                questions:
                  - slug: int-nl-order-ascending
                    # mcq_single | mcq_multi | numeric | symbolic | multi_part
                    type: mcq_single
                    difficulty: easy         # easy | medium | hard
                    body: "Which list is in ascending order?"
                    answer_schema:
                      options:
                        - {id: a, text: "-1, -3, 0, 2"}
                        - {id: b, text: "-3, -1, 0, 2"}
                      correct_option: b
                    worked_solution: "On a number line ..."
                    skill_tags: ["ordering integers"]
```

`slug` is the stable natural key at every level; re-running the ingest matches
rows by it. Lecture bodies live in separate Markdown files referenced by
`lecture_file`, resolved relative to the manifest.

Two entry points, both raising `ManifestError` (never a bare `ValidationError`)
for anything an author can fix:

* `parse_manifest(data, lecture_loader=...)` — validates an already-loaded
  mapping. `data` + a `lecture_loader` callable is exactly what a future admin
  upload UI holds, so it calls this directly; the CLI is only a wrapper.
* `load_manifest_file(path)` — reads the YAML at `path` and wires a loader that
  reads sibling files.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.cas import expression_parses
from app.ingest.errors import ManifestError
from app.models import (
    CONTENT_DRAFT,
    CONTENT_PUBLISHED,
    DIFFICULTY_EASY,
    DIFFICULTY_HARD,
    DIFFICULTY_MEDIUM,
    QUESTION_MCQ_MULTI,
    QUESTION_MCQ_SINGLE,
    QUESTION_MULTI_PART,
    QUESTION_NUMERIC,
    QUESTION_SYMBOLIC,
)

# A loader turns a `lecture_file` reference into its Markdown body. The CLI
# reads sibling files; an upload UI would read from the uploaded bundle.
LectureLoader = Callable[[str], str]

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_STATUSES = {CONTENT_DRAFT, CONTENT_PUBLISHED}
_DIFFICULTIES = {DIFFICULTY_EASY, DIFFICULTY_MEDIUM, DIFFICULTY_HARD}
_QUESTION_TYPES = {
    QUESTION_MCQ_SINGLE,
    QUESTION_MCQ_MULTI,
    QUESTION_NUMERIC,
    QUESTION_SYMBOLIC,
    QUESTION_MULTI_PART,
}
# A `multi_part` part is itself one of the other types — no nesting.
_PART_TYPES = _QUESTION_TYPES - {QUESTION_MULTI_PART}
_SYMBOLIC_DOMAINS = {"real", "positive", "complex"}


def _check_slug(value: str) -> str:
    if not _SLUG_RE.match(value):
        raise ValueError(
            f"{value!r} is not a valid slug "
            "(lowercase letters, digits, single hyphens)"
        )
    return value


class _Node(BaseModel):
    # Reject unknown keys so a typo'd field name is an error, not a silent no-op.
    model_config = ConfigDict(extra="forbid")


class QuestionSpec(_Node):
    slug: str
    type: str
    difficulty: str
    body: str = Field(min_length=1)
    answer_schema: dict[str, Any]
    worked_solution: str = Field(min_length=1)
    skill_tags: list[str] = Field(default_factory=list)

    @field_validator("slug")
    @classmethod
    def _slug_ok(cls, v: str) -> str:
        return _check_slug(v)

    @field_validator("skill_tags")
    @classmethod
    def _tags_ok(cls, v: list[str]) -> list[str]:
        cleaned = [t.strip() for t in v]
        if any(not t for t in cleaned):
            raise ValueError("skill tag names must not be blank")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("a skill tag is listed twice on one question")
        return cleaned

    @model_validator(mode="after")
    def _type_difficulty_and_schema(self) -> "QuestionSpec":
        if self.type not in _QUESTION_TYPES:
            raise ValueError(
                f"unknown question type {self.type!r} "
                f"(expected one of {sorted(_QUESTION_TYPES)})"
            )
        if self.difficulty not in _DIFFICULTIES:
            raise ValueError(
                f"unknown difficulty {self.difficulty!r} "
                f"(expected one of {sorted(_DIFFICULTIES)})"
            )
        _check_answer_schema(self.type, self.answer_schema)
        return self


def _check_answer_schema(qtype: str, schema: dict[str, Any]) -> None:
    """Reject an `answer_schema` that would not grade — while it is still cheap
    author feedback rather than a runtime surprise. `app/practice/grading.py`
    owns the shape at runtime; this mirrors the keys it reads, per `type`."""
    if qtype in (QUESTION_MCQ_SINGLE, QUESTION_MCQ_MULTI):
        options = schema.get("options")
        if not isinstance(options, list) or not options:
            raise ValueError("mcq answer_schema needs a non-empty 'options' list")
        ids: list[str] = []
        for opt in options:
            if not isinstance(opt, dict) or "id" not in opt or "text" not in opt:
                raise ValueError("each mcq option needs an 'id' and a 'text'")
            ids.append(str(opt["id"]))
        if len(set(ids)) != len(ids):
            raise ValueError("mcq option ids must be unique")
        if qtype == QUESTION_MCQ_SINGLE:
            if "correct_option" not in schema:
                raise ValueError("mcq_single answer_schema needs 'correct_option'")
            if str(schema["correct_option"]) not in ids:
                raise ValueError(
                    f"correct_option {schema['correct_option']!r} "
                    "is not one of the option ids"
                )
        else:
            correct = schema.get("correct_options")
            if not isinstance(correct, list) or not correct:
                raise ValueError(
                    "mcq_multi answer_schema needs a non-empty "
                    "'correct_options' list"
                )
            unknown = [c for c in correct if str(c) not in ids]
            if unknown:
                raise ValueError(
                    f"correct_options {unknown!r} are not option ids"
                )
    elif qtype == QUESTION_NUMERIC:
        if "value" not in schema:
            raise ValueError("numeric answer_schema needs a 'value'")
        try:
            float(schema["value"])
        except (TypeError, ValueError):
            raise ValueError("numeric 'value' must be a number")
        try:
            tolerance = float(schema.get("tolerance", 0))
        except (TypeError, ValueError):
            raise ValueError("numeric 'tolerance' must be a number")
        if tolerance < 0:
            raise ValueError("numeric 'tolerance' must not be negative")
    elif qtype == QUESTION_SYMBOLIC:
        expression = schema.get("expression")
        if not isinstance(expression, str) or not expression.strip():
            raise ValueError(
                "symbolic answer_schema needs a non-empty 'expression'"
            )
        variables = schema.get("variables", [])
        if not isinstance(variables, list) or any(
            not isinstance(v, str) or not v.strip() for v in variables
        ):
            raise ValueError(
                "symbolic 'variables' must be a list of variable names"
            )
        domain = schema.get("domain", "real")
        if domain not in _SYMBOLIC_DOMAINS:
            raise ValueError(
                f"unknown symbolic domain {domain!r} "
                f"(expected one of {sorted(_SYMBOLIC_DOMAINS)})"
            )
        if not expression_parses(
            expression, variables=variables, domain=domain
        ):
            raise ValueError(
                f"symbolic 'expression' {expression!r} is not a "
                "well-formed expression"
            )
    elif qtype == QUESTION_MULTI_PART:
        parts = schema.get("parts")
        if not isinstance(parts, list) or not parts:
            raise ValueError(
                "multi_part answer_schema needs a non-empty 'parts' list"
            )
        part_ids: list[str] = []
        for part in parts:
            if not isinstance(part, dict):
                raise ValueError("each multi_part part must be a mapping")
            if "id" not in part:
                raise ValueError("each multi_part part needs an 'id'")
            part_ids.append(str(part["id"]))
            body = part.get("body")
            if not isinstance(body, str) or not body.strip():
                raise ValueError(
                    "each multi_part part needs a non-empty 'body' prompt"
                )
            ptype = part.get("type")
            if ptype not in _PART_TYPES:
                raise ValueError(
                    f"unknown multi_part part type {ptype!r} "
                    f"(expected one of {sorted(_PART_TYPES)})"
                )
            part_schema = part.get("answer_schema")
            if not isinstance(part_schema, dict):
                raise ValueError(
                    "each multi_part part needs an 'answer_schema' mapping"
                )
            _check_answer_schema(ptype, part_schema)
        if len(set(part_ids)) != len(part_ids):
            raise ValueError("multi_part part ids must be unique")


class TopicSpec(_Node):
    slug: str
    title: str = Field(min_length=1)
    order: int
    lecture_file: str = Field(min_length=1)
    status: str = CONTENT_PUBLISHED
    prerequisites: list[str] = Field(default_factory=list)
    questions: list[QuestionSpec] = Field(default_factory=list)
    # Filled in by `parse_manifest` from `lecture_file` via the loader; not an
    # input key.
    lecture_body: str = ""

    @field_validator("slug")
    @classmethod
    def _slug_ok(cls, v: str) -> str:
        return _check_slug(v)

    @field_validator("status")
    @classmethod
    def _status_ok(cls, v: str) -> str:
        if v not in _STATUSES:
            raise ValueError(
                f"unknown status {v!r} (expected one of {sorted(_STATUSES)})"
            )
        return v

    @field_validator("prerequisites")
    @classmethod
    def _prereqs_ok(cls, v: list[str]) -> list[str]:
        for slug in v:
            _check_slug(slug)
        if len(set(v)) != len(v):
            raise ValueError("a prerequisite is listed twice")
        return v


class UnitSpec(_Node):
    slug: str
    title: str = Field(min_length=1)
    order: int
    topics: list[TopicSpec] = Field(min_length=1)

    @field_validator("slug")
    @classmethod
    def _slug_ok(cls, v: str) -> str:
        return _check_slug(v)


class SubjectSpec(_Node):
    slug: str
    title: str = Field(min_length=1)
    order: int
    units: list[UnitSpec] = Field(min_length=1)

    @field_validator("slug")
    @classmethod
    def _slug_ok(cls, v: str) -> str:
        return _check_slug(v)


class YearLevelSpec(_Node):
    slug: str
    name: str = Field(min_length=1)
    syllabus_region: str = Field(min_length=1)
    subjects: list[SubjectSpec] = Field(min_length=1)

    @field_validator("slug")
    @classmethod
    def _slug_ok(cls, v: str) -> str:
        return _check_slug(v)


class Manifest(_Node):
    year_levels: list[YearLevelSpec] = Field(min_length=1)

    def iter_topics(self):
        """Every `TopicSpec`, in tree order."""
        for yl in self.year_levels:
            for subject in yl.subjects:
                for unit in subject.units:
                    yield from unit.topics


def _format_validation_error(exc: ValidationError) -> str:
    lines = ["manifest failed validation:"]
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(root)"
        lines.append(f"  - {loc}: {err['msg']}")
    return "\n".join(lines)


def _check_slug_uniqueness(manifest: Manifest) -> None:
    buckets: dict[str, list[str]] = {
        "year level": [],
        "subject": [],
        "unit": [],
        "topic": [],
        "question": [],
    }
    for yl in manifest.year_levels:
        buckets["year level"].append(yl.slug)
        for subject in yl.subjects:
            buckets["subject"].append(subject.slug)
            for unit in subject.units:
                buckets["unit"].append(unit.slug)
                for topic in unit.topics:
                    buckets["topic"].append(topic.slug)
                    for question in topic.questions:
                        buckets["question"].append(question.slug)

    problems: list[str] = []
    for kind, slugs in buckets.items():
        seen: set[str] = set()
        for slug in slugs:
            if slug in seen:
                problems.append(f"{kind} slug {slug!r} is used more than once")
            seen.add(slug)
    if problems:
        raise ManifestError(
            "duplicate slugs:\n  - " + "\n  - ".join(problems)
        )


def _check_prerequisites(manifest: Manifest) -> None:
    topic_slugs = {topic.slug for topic in manifest.iter_topics()}
    problems: list[str] = []
    for topic in manifest.iter_topics():
        for prereq in topic.prerequisites:
            if prereq == topic.slug:
                problems.append(
                    f"topic {topic.slug!r} lists itself as a prerequisite"
                )
            elif prereq not in topic_slugs:
                problems.append(
                    f"topic {topic.slug!r} has prerequisite {prereq!r}, "
                    "which is not a topic in this manifest"
                )
    if problems:
        raise ManifestError(
            "bad prerequisite references:\n  - " + "\n  - ".join(problems)
        )


def _check_lecture_bodies(manifest: Manifest) -> None:
    blank = [t.slug for t in manifest.iter_topics() if not t.lecture_body.strip()]
    if blank:
        raise ManifestError(
            "topics have no lecture body (lecture file empty or unresolved):"
            "\n  - " + "\n  - ".join(blank)
        )


def _resolve_lectures(manifest: Manifest, loader: LectureLoader) -> None:
    for topic in manifest.iter_topics():
        topic.lecture_body = loader(topic.lecture_file)
    _check_lecture_bodies(manifest)


def assert_manifest_consistent(manifest: Manifest) -> None:
    """Cross-entity checks that need no I/O: slugs unique within each kind,
    every prerequisite resolves to a topic in the manifest, every topic has a
    non-empty `lecture_body`.

    `parse_manifest` runs these while loading; `ingest_manifest` runs them again
    at the top so a caller that builds a `Manifest` by hand (the admin-upload-UI
    path the module docstring describes) is held to the same guarantees.
    """
    _check_slug_uniqueness(manifest)
    _check_prerequisites(manifest)
    _check_lecture_bodies(manifest)


def parse_manifest(data: Any, *, lecture_loader: LectureLoader) -> Manifest:
    """Validate `data` (a mapping already loaded from YAML/JSON) and return a
    `Manifest` with every topic's `lecture_body` resolved via `lecture_loader`.

    Raises `ManifestError` for any author-fixable problem; no side effects.
    """
    if not isinstance(data, dict):
        raise ManifestError(
            "manifest root must be a mapping with a 'year_levels' key"
        )
    try:
        manifest = Manifest.model_validate(data)
    except ValidationError as exc:
        raise ManifestError(_format_validation_error(exc)) from exc

    _check_slug_uniqueness(manifest)  # early, before any file I/O
    _resolve_lectures(manifest, lecture_loader)
    _check_prerequisites(manifest)
    return manifest


def load_manifest_file(path: str | Path) -> Manifest:
    """Read the manifest YAML at `path` and resolve lecture files relative to
    its directory. Raises `ManifestError` for a missing/instringable file,
    invalid YAML, or any validation failure."""
    manifest_path = Path(path)
    try:
        raw = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestError(
            f"cannot read manifest {manifest_path}: {exc}"
        ) from exc
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ManifestError(f"manifest is not valid YAML: {exc}") from exc

    base_dir = manifest_path.parent.resolve()

    def _loader(ref: str) -> str:
        target = (base_dir / ref).resolve()
        try:
            target.relative_to(base_dir)
        except ValueError:
            raise ManifestError(
                f"lecture file {ref!r} escapes the manifest directory"
            )
        try:
            return target.read_text(encoding="utf-8")
        except OSError as exc:
            raise ManifestError(
                f"cannot read lecture file {ref!r}: {exc}"
            ) from exc

    return parse_manifest(data, lecture_loader=_loader)
