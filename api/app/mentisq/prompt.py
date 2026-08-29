"""The guided-mode system prompt: a versioned template file plus the code that
renders it.

`prompts/<version>.md` holds the guided-mode rules (no final answer on the first
reply; full worked solution only on explicit request; on shared work, name the
wrong step; stay in maths; render maths as LaTeX). When the student launches
from a Topic or Question, that context (statement, correct answer, worked
solution) is injected into the `{context}` slot — it is reference material for
the tutor and is never returned verbatim to the student.

Keep the wire format a single prompt string (the `MentisQLLMClient` boundary
takes `prompt=`): system rules, then the injected context, then the student's
message.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# Bump this (and add a sibling `prompts/<version>.md`) when the guided-mode
# rules change; the version travels with the code, not the database.
GUIDED_PROMPT_VERSION = "guided_v1"

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# How much of a lecture body to hand the tutor as the Topic "statement".
_LECTURE_EXCERPT_CHARS = 2000


@dataclass(frozen=True)
class PromptContext:
    """The Topic- or Question-scoped material injected into the system prompt.
    Every field is optional; an all-empty context renders no context block.
    """

    topic_title: str | None = None
    lecture_excerpt: str | None = None
    question_body: str | None = None
    correct_answer: str | None = None
    worked_solution: str | None = None

    def is_empty(self) -> bool:
        return not any(
            (
                self.topic_title,
                self.lecture_excerpt,
                self.question_body,
                self.correct_answer,
                self.worked_solution,
            )
        )


@lru_cache(maxsize=None)
def _template() -> str:
    return (_PROMPTS_DIR / f"{GUIDED_PROMPT_VERSION}.md").read_text(
        encoding="utf-8"
    )


def _context_block(context: PromptContext | None) -> str:
    if context is None or context.is_empty():
        return ""
    fields = [
        ("Topic", context.topic_title),
        ("Lecture material", context.lecture_excerpt),
        ("Question", context.question_body),
        ("Correct answer", context.correct_answer),
        ("Worked solution", context.worked_solution),
    ]
    lines = [
        "## Problem context (for your reference only — never quote this back "
        "to the student verbatim)",
        "",
    ]
    lines += [f"{label}: {value}" for label, value in fields if value]
    return "\n".join(lines)


def lecture_excerpt(body: str | None) -> str | None:
    """Trim a lecture body to the size the tutor gets as context."""
    if not body:
        return None
    body = body.strip()
    if len(body) <= _LECTURE_EXCERPT_CHARS:
        return body
    return body[:_LECTURE_EXCERPT_CHARS].rstrip() + "…"


def render_system_prompt(context: PromptContext | None = None) -> str:
    return _template().replace("{context}", _context_block(context)).strip()


def build_prompt(
    user_message: str, context: PromptContext | None = None
) -> str:
    """The full single-string prompt sent to the provider."""
    system = render_system_prompt(context)
    return f"{system}\n\n---\n\nStudent: {user_message.strip()}"
