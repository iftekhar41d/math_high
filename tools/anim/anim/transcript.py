"""Auto-generate the caption / transcript sidecar (``.vtt``).

v1 is deliberately simple: the LLM returns an ordered list of caption lines, and
:func:`to_vtt` spreads them evenly across the animation's duration. There is no
word-level timing and no TTS (both deferred). The result is a valid WebVTT file
the ContentAdmin uploads alongside the ``.mp4``; it is also what makes the
animation publishable (a transcript is required to publish — ticket 10/11).

Pure seams: :func:`parse_caption_lines`, :func:`to_vtt`.
"""

from __future__ import annotations

import re

from .config import Config
from .llm import LLMClient
from .prompt import TRANSCRIPT_SYSTEM, transcript_user_message

_LIST_PREFIX_RE = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s*")
_MIN_CUE_SECONDS = 1.5


class TranscriptError(RuntimeError):
    """The model reply held no caption lines, or the .vtt could not be built."""


def parse_caption_lines(text: str) -> list[str]:
    """Strip list markers / blank lines from an LLM reply -> ordered cue texts."""
    lines = []
    for raw in text.splitlines():
        line = _LIST_PREFIX_RE.sub("", raw).strip()
        if line:
            lines.append(line)
    if not lines:
        raise TranscriptError("no caption lines found in the model reply")
    return lines


def _fmt_ts(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def to_vtt(lines: list[str], duration_seconds: float | None) -> str:
    """Lay ``lines`` out as evenly-spaced WebVTT cues over ``duration_seconds``.

    When the duration is unknown, fall back to a fixed per-line estimate so the
    file is still valid and roughly paced.
    """
    if not lines:
        raise TranscriptError("cannot build a .vtt from zero lines")
    total = duration_seconds
    if not total or total <= 0:
        total = len(lines) * 4.0  # no probe available — a rough per-line estimate
    step = max(total / len(lines), _MIN_CUE_SECONDS)

    out = ["WEBVTT", ""]
    for i, line in enumerate(lines):
        start = i * step
        end = total if i == len(lines) - 1 else (i + 1) * step
        if end <= start:
            end = start + _MIN_CUE_SECONDS
        out.append(str(i + 1))
        out.append(f"{_fmt_ts(start)} --> {_fmt_ts(end)}")
        out.append(line)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def generate_transcript(
    client: LLMClient,
    config: Config,
    *,
    idea: str,
    script: str,
    duration_seconds: float | None,
) -> str:
    """LLM caption lines -> a WebVTT string."""
    messages = [
        {"role": "system", "content": TRANSCRIPT_SYSTEM},
        {"role": "user", "content": transcript_user_message(idea, script)},
    ]
    reply = client.complete(messages=messages, model=config.model)
    return to_vtt(parse_caption_lines(reply), duration_seconds)
