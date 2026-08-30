"""Orchestration: idea -> reviewed ``.mp4`` + ``.vtt``.

    idea (text)
      -> LLM drafts a Manim scene script            (scriptgen)
      -> save idea.txt + scene.py under scenes/<slug>/   (scene_store)
      -> render; on failure feed the traceback back and retry, bounded  (render)
      -> LLM writes a transcript, laid out as WebVTT   (transcript)
      -> a human reviewer approves or rejects
           approve -> done: artifacts ready to upload via ticket 11
           reject  -> regenerate with the note, re-render, re-review (bounded)

The reviewer is injected (a callable ``ReviewRequest -> ReviewDecision``) so the
CLI can prompt interactively and the smoke test can stub it. Nothing here writes
to the app DB or the media store — the ContentAdmin screen owns the upload.

Every render for a slug goes into its own ``<out_dir>/<slug>/media`` tree so two
slugs rendered into the same ``out_dir`` never collide.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import scene_store, scriptgen, transcript
from .config import Config
from .llm import LLMClient
from .render import RenderResult, probe_duration_seconds, render_scene


class PipelineError(RuntimeError):
    """A stage failed in a way retrying will not fix (or retries were exhausted)."""


@dataclass(frozen=True)
class ReviewRequest:
    slug: str
    generation: int  # 1 for the first draft the human sees
    script_path: Path
    video_path: Path
    transcript_path: Path
    duration_seconds: float | None
    render_attempts: int  # renders it took to get here this generation


@dataclass(frozen=True)
class ReviewDecision:
    approved: bool
    note: str | None = None  # rejection feedback, fed into the next generation


Reviewer = Callable[[ReviewRequest], ReviewDecision]


@dataclass(frozen=True)
class AnimationArtifacts:
    slug: str
    scene_dir: Path
    script_path: Path
    video_path: Path
    transcript_path: Path
    duration_seconds: float | None
    generations: int  # how many script generations the human saw (1 = approved first)
    render_attempts: int  # renders in the final generation


@dataclass(frozen=True)
class _Generation:
    """The output of one full script generation (draft/revise + render + vtt)."""

    video_path: Path
    transcript_path: Path
    duration_seconds: float | None
    render_attempts: int


def _slug_out(out_dir: Path, slug: str) -> Path:
    d = out_dir / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def _copy_rendered_video(result: RenderResult, out_dir: Path, slug: str) -> Path:
    """Copy Manim's output to the stable ``<out_dir>/<slug>/<slug>.mp4``."""
    assert result.video_path is not None
    dest = _slug_out(out_dir, slug) / f"{slug}.mp4"
    shutil.copyfile(result.video_path, dest)
    return dest


def render_once(
    script_path: Path,
    scene_name: str,
    *,
    slug: str,
    out_dir: Path,
    quality: str,
) -> Path:
    """Render ``script_path`` a single time (no LLM, no retry) and return the
    path to the copied ``.mp4``. Raises :class:`PipelineError` on failure. This
    is the ``author.py --rerender`` path."""
    result = render_scene(
        script_path, scene_name, out_dir=_slug_out(out_dir, slug), quality=quality
    )
    if not result.ok:
        raise PipelineError(result.traceback or "render failed with no output")
    return _copy_rendered_video(result, out_dir, slug)


def _render_with_retries(
    client: LLMClient,
    config: Config,
    *,
    idea: str,
    slug: str,
    scene_name: str,
    out_dir: Path,
    script: str,
) -> tuple[str, RenderResult, int]:
    """Render ``script``; on failure feed the traceback back to the LLM and
    retry, up to ``config.render_retries`` extra attempts. Returns the script
    that rendered, its :class:`RenderResult`, and the attempt count.
    """
    script_path = scene_store.script_path(slug)
    slug_media = _slug_out(out_dir, slug)
    attempts = 0
    last: RenderResult | None = None
    for attempt in range(config.render_retries + 1):
        attempts = attempt + 1
        result = render_scene(
            script_path, scene_name, out_dir=slug_media, quality=config.render_quality
        )
        if result.ok:
            return script, result, attempts
        last = result
        if attempt == config.render_retries:
            break
        script = scriptgen.generate_scene_script(
            client,
            config,
            idea=idea,
            scene_name=scene_name,
            previous_script=script,
            render_traceback=result.traceback,
        )
        scene_store.save(slug, idea=idea, script=script)

    assert last is not None
    raise PipelineError(
        f"render failed after {attempts} attempt(s). The last script + idea are "
        f"in {scene_store.scene_dir(slug)} for a hand-edit. Last traceback:\n"
        f"{last.traceback}"
    )


def _generate_once(
    client: LLMClient,
    config: Config,
    *,
    idea: str,
    slug: str,
    scene_name: str,
    out_dir: Path,
    previous_script: str | None,
    rejection_note: str | None,
) -> _Generation:
    """One full generation: draft (or revise) the script, render it with
    retries, then write the transcript."""
    script = scriptgen.generate_scene_script(
        client,
        config,
        idea=idea,
        scene_name=scene_name,
        previous_script=previous_script,
        rejection_note=rejection_note,
    )
    scene_store.save(slug, idea=idea, script=script)

    final_script, result, render_attempts = _render_with_retries(
        client,
        config,
        idea=idea,
        slug=slug,
        scene_name=scene_name,
        out_dir=out_dir,
        script=script,
    )
    video_path = _copy_rendered_video(result, out_dir, slug)

    duration = probe_duration_seconds(video_path)
    vtt = transcript.generate_transcript(
        client,
        config,
        idea=idea,
        script=final_script,
        duration_seconds=duration,
    )
    transcript_path = _slug_out(out_dir, slug) / f"{slug}.vtt"
    transcript_path.write_text(vtt, encoding="utf-8")
    return _Generation(
        video_path=video_path,
        transcript_path=transcript_path,
        duration_seconds=duration,
        render_attempts=render_attempts,
    )


def author_animation(
    client: LLMClient,
    config: Config,
    *,
    idea: str,
    slug: str,
    out_dir: Path,
    reviewer: Reviewer,
    scene_name: str | None = None,
    max_regenerations: int = 3,
    seed_script: str | None = None,
    seed_rejection_note: str | None = None,
) -> AnimationArtifacts:
    """Run the full pipeline and return the approved artifacts.

    ``seed_script`` / ``seed_rejection_note`` resume from an existing
    ``scenes/<slug>/scene.py`` plus a reviewer note (the "reject this old one and
    try again" entry point). ``reviewer`` is called once per generation; a
    rejection note is fed into the next. Raises :class:`PipelineError` if the
    reviewer keeps rejecting past ``max_regenerations``.
    """
    scene_store.validate_slug(slug)
    scene_name = scene_name or scriptgen.scene_name_for(slug)

    previous_script = seed_script
    rejection_note = seed_rejection_note

    for generation in range(1, max_regenerations + 2):
        gen = _generate_once(
            client,
            config,
            idea=idea,
            slug=slug,
            scene_name=scene_name,
            out_dir=out_dir,
            previous_script=previous_script,
            rejection_note=rejection_note,
        )
        decision = reviewer(
            ReviewRequest(
                slug=slug,
                generation=generation,
                script_path=scene_store.script_path(slug),
                video_path=gen.video_path,
                transcript_path=gen.transcript_path,
                duration_seconds=gen.duration_seconds,
                render_attempts=gen.render_attempts,
            )
        )
        if decision.approved:
            return AnimationArtifacts(
                slug=slug,
                scene_dir=scene_store.scene_dir(slug),
                script_path=scene_store.script_path(slug),
                video_path=gen.video_path,
                transcript_path=gen.transcript_path,
                duration_seconds=gen.duration_seconds,
                generations=generation,
                render_attempts=gen.render_attempts,
            )
        previous_script = scene_store.load(slug).script
        rejection_note = (
            (decision.note or "").strip() or "The reviewer rejected it without a note."
        )

    raise PipelineError(
        f"still rejected after {max_regenerations} regeneration(s). The last "
        f"script and idea are in {scene_store.scene_dir(slug)} for a hand-edit."
    )
