"""Idea (plus optional feedback) -> a Manim scene script string.

The pure seam here is :func:`extract_scene_code` — pulling a runnable script out
of an LLM reply — and :func:`scene_name_for`. :func:`generate_scene_script` wires
them to the LLM client.
"""

from __future__ import annotations

import re

from .config import Config
from .llm import LLMClient
from .prompt import SCRIPT_SYSTEM, script_user_message

_FENCE_RE = re.compile(
    r"```(?:python|py)?[ \t]*\r?\n(.*?)\r?\n```",
    re.DOTALL | re.IGNORECASE,
)


class ScriptGenerationError(RuntimeError):
    """The model reply held no usable script."""


def scene_name_for(slug: str) -> str:
    """A valid, stable PascalCase ``Scene`` subclass name derived from the slug.

    ``"adding-fractions"`` -> ``"AddingFractionsScene"``. Always ends in
    ``Scene`` and always starts with a letter.
    """
    parts = re.split(r"[^0-9A-Za-z]+", slug.strip())
    name = "".join(p[:1].upper() + p[1:] for p in parts if p)
    if not name or not name[0].isalpha():
        name = "Anim" + name
    if not name.endswith("Scene"):
        name += "Scene"
    return name


def extract_scene_code(text: str) -> str:
    """Return the Python script from an LLM reply.

    Prefers the first fenced ```python block. Falls back to the whole reply when
    it is unfenced but clearly a script (imports manim and defines a Scene).
    Raises :class:`ScriptGenerationError` otherwise.
    """
    match = _FENCE_RE.search(text)
    candidate = match.group(1) if match else text
    candidate = candidate.strip()
    looks_like_script = (
        "manim" in candidate
        and re.search(r"class\s+\w+\s*\(\s*\w*Scene\w*\s*\)", candidate) is not None
    )
    if not looks_like_script:
        raise ScriptGenerationError(
            "The model did not return a Manim script (no `manim` import or "
            "`Scene` subclass found)."
        )
    if not candidate.endswith("\n"):
        candidate += "\n"
    return candidate


def generate_scene_script(
    client: LLMClient,
    config: Config,
    *,
    idea: str,
    scene_name: str,
    previous_script: str | None = None,
    render_traceback: str | None = None,
    rejection_note: str | None = None,
) -> str:
    """One LLM round-trip. First draft, render-fix retry, or rejection redo —
    which one is decided by the optional args (see
    :func:`anim.prompt.script_user_message`)."""
    messages = [
        {"role": "system", "content": SCRIPT_SYSTEM},
        {
            "role": "user",
            "content": script_user_message(
                idea,
                scene_name,
                previous_script=previous_script,
                render_traceback=render_traceback,
                rejection_note=rejection_note,
            ),
        },
    ]
    reply = client.complete(messages=messages, model=config.model)
    return extract_scene_code(reply)
