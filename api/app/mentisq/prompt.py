"""The guided-mode system prompt: a versioned template file plus the code that
renders it.

`prompts/<version>.md` holds the guided-mode rules (no final answer on the first
assistant turn of the session; full worked solution only on explicit request; on
shared work, name the wrong step; stay in maths; render maths as LaTeX). When the
student launches from a Topic or Question, that context (statement, correct
answer, worked solution) is injected into the `{context}` slot — it is reference
material for the tutor and is never returned verbatim to the student.

The wire format is an OpenAI-style message list (the `MentisQLLMClient` boundary
takes `messages=`): a `system` message carrying the rules + injected context,
then the recent conversation turns, then the student's new `user` message.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol

# Bump this (and add a sibling `prompts/<version>.md`) when the guided-mode
# rules change; the version travels with the code, not the database. It is
# stamped onto each `MentisQSession` at creation.
GUIDED_PROMPT_VERSION = "guided_v2"

# How many trailing conversation messages (user + assistant turns combined) are
# replayed to the model. Older turns are dropped, not summarised.
HISTORY_MAX_MESSAGES = 12

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


class _Turn(Protocol):
    """A stored conversation turn — `MentisQMessage` satisfies this."""

    role: str  # "user" | "assistant"
    content: str


def build_messages(
    user_message: str,
    context: PromptContext | None = None,
    history: list[_Turn] | None = None,
    *,
    is_continuation: bool = False,
) -> list[dict[str, str]]:
    """The OpenAI-style message list sent to the provider: the guided-mode
    `system` message (rules + any injected context), then the recent
    conversation `history` in order, then the student's new `user` message.

    `history` is expected to already be trimmed to `HISTORY_MAX_MESSAGES` and to
    exclude `failed` turns; this function does not filter it. `is_continuation`
    states plainly whether prior assistant turns exist, so the first-turn rule
    holds even once the earliest turns have fallen outside the replay window.
    """
    turn_state = (
        "This is a continuation of an ongoing session — earlier turns may fall "
        "outside the excerpt above, so this is NOT the first assistant turn."
        if is_continuation
        else "This is the FIRST assistant turn of the session."
    )
    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": f"{render_system_prompt(context)}\n\n{turn_state}",
        }
    ]
    for turn in history or []:
        messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": user_message.strip()})
    return messages
