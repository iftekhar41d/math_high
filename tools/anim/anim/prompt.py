"""The system + user prompts the toolchain sends.

Two jobs, two prompts:

- ``SCRIPT_SYSTEM`` / ``script_user_message`` — draft (or revise) a single-file
  Manim scene. Revisions carry either a render traceback or a human rejection
  note as the thing to fix.
- ``TRANSCRIPT_SYSTEM`` / ``transcript_user_message`` — turn the final idea +
  script into an ordered list of plain caption lines, which ``transcript.py``
  lays out as WebVTT.

The prompts are plain constants here (not versioned template files like
``app/mentisq/prompts/``): this is an author-time dev tool, not a
student-facing surface with a pedagogy contract to pin.
"""

from __future__ import annotations

# Design-system palette (CLAUDE.md) — the animations must look like the app.
_PALETTE = (
    "Background #F9F7F7, Accent #DBE2EF, Primary #3F72AF, Dark/Text #112D4E. "
    "Use ONLY these four hex values."
)

SCRIPT_SYSTEM = f"""\
You are an expert Manim (Community Edition v0.18) developer writing short
explainer animations for a Year 7 Mathematics learning platform (NSW, Australia).

Output rules — follow every one:
- Reply with EXACTLY ONE fenced Python code block (```python ... ```) and nothing
  else. No prose before or after.
- The file must define exactly one `Scene` subclass. Its class name is given to
  you in the request — use that name verbatim so the renderer can find it.
- `from manim import *` at the top. Standard library imports are fine. Do NOT
  import anything else, and do NOT read external files, fonts, images, SVGs, or
  network resources — the script must render standalone.
- Silent animation only: never call `self.add_sound(...)` or reference audio.
- Keep it 15-45 seconds of `self.play(...)` / `self.wait(...)`. End with a short
  `self.wait(1)`.
- Mathematically correct and age-appropriate for Year 7. Prefer `MathTex` /
  `Tex` for maths; a working LaTeX install is available.
- Visual style: {_PALETTE} Set the frame background with
  `self.camera.background_color`. Keep text on screen long enough to read.
- No `config.*` mutation, no `if __name__ == "__main__"` block, no CLI code.
- The code must run under `manim render` with no arguments beyond scene
  selection.
"""

TRANSCRIPT_SYSTEM = """\
You write concise, accurate captions/transcripts for a silent maths explainer
animation. You are given the original idea and the final Manim script.

Output rules:
- Reply with a plain numbered list, one caption line per list item, in the order
  they appear on screen.
- Each line is one short sentence (<= ~12 words) describing what is shown or the
  point being made. Spell out any maths in words (e.g. "two x plus three").
- 4 to 12 lines total. No timestamps, no markdown, no preamble.
"""


def script_user_message(
    idea: str,
    scene_name: str,
    *,
    previous_script: str | None = None,
    render_traceback: str | None = None,
    rejection_note: str | None = None,
) -> str:
    """Build the user turn for script generation or revision.

    A first draft passes only ``idea`` + ``scene_name``. A retry after a failed
    render passes ``previous_script`` + ``render_traceback``. A regeneration
    after a human rejection passes ``previous_script`` + ``rejection_note``.
    """
    parts = [
        f"Idea:\n{idea.strip()}",
        f"\nScene class name (use exactly): {scene_name}",
    ]
    if previous_script and render_traceback:
        parts.append(
            "\nThe previous script below failed to render. Fix the cause of the "
            "traceback and return the full corrected script.\n\n"
            f"--- previous script ---\n{previous_script.strip()}\n"
            f"--- render traceback ---\n{render_traceback.strip()}"
        )
    elif previous_script and rejection_note:
        parts.append(
            "\nA human reviewer rejected the previous script with the note "
            "below. Address it and return the full revised script.\n\n"
            f"--- previous script ---\n{previous_script.strip()}\n"
            f"--- reviewer note ---\n{rejection_note.strip()}"
        )
    return "\n".join(parts)


def transcript_user_message(idea: str, script: str) -> str:
    return (
        f"Original idea:\n{idea.strip()}\n\n"
        f"Final Manim script:\n{script.strip()}"
    )
