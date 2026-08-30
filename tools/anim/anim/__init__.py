"""`tools/anim/` — the animation authoring toolchain.

A ContentAdmin (or a developer) runs this OFF the VPS to turn a plain-language
idea into a reviewed animation: an LLM drafts a Manim scene script, the tool
renders it, feeds any render traceback back and retries up to a small bound, then
hands back a silent ``.mp4`` plus a ``.vtt`` transcript for a human to approve or
reject. The idea text and the final script are kept under ``scenes/<slug>/`` so
the animation can be re-rendered or hand-edited later; the ``.mp4`` + ``.vtt`` are
uploaded through the ContentAdmin animation screen (Phase 2 ticket 11).

Nothing in this package is installed into the API venv or run on the VPS
(``docs/adr/0004``). It reuses ``OPENROUTER_API_KEY`` but reads its own
``ANIM_LLM_MODEL`` and never touches MentisQ spend or caps.
"""

from __future__ import annotations

__all__ = ["config", "llm", "prompt", "scriptgen", "render", "transcript", "scene_store", "pipeline"]
