#!/usr/bin/env python
"""CLI entry point for the animation authoring toolchain.

Run from ``tools/anim/`` (so ``import anim`` resolves), with the toolchain venv
active:

    python author.py --slug adding-fractions --idea "Show why 1/2 + 1/3 = 5/6 ..."
    python author.py --slug adding-fractions --idea-file idea.txt
    python author.py --slug adding-fractions --from-scene \\
        --reject-note "the denominators overlap the title — move them down"
    python author.py --slug adding-fractions --rerender      # no LLM, just render scene.py

On approval it prints the ``.mp4`` + ``.vtt`` paths to upload through the
ContentAdmin animation screen, and reminds you to commit ``scenes/<slug>/``.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

from anim import scene_store, scriptgen
from anim.config import (
    DEFAULT_OUT_DIR,
    DEFAULT_RENDER_QUALITY,
    RENDER_QUALITIES,
    ConfigError,
    load_config,
)
from anim.llm import AnimLLMError, get_client
from anim.pipeline import (
    PipelineError,
    ReviewDecision,
    ReviewRequest,
    author_animation,
    render_once,
)
from anim.render import RenderUnavailable


def _read_idea(args: argparse.Namespace) -> str:
    if args.idea_file:
        return Path(args.idea_file).read_text(encoding="utf-8").strip()
    if args.idea:
        return args.idea.strip()
    if args.from_scene or args.rerender:
        # Reuse the idea already committed next to the scene.
        return scene_store.load(args.slug).idea.strip()
    raise SystemExit("error: one of --idea / --idea-file is required")


def _interactive_reviewer(req: ReviewRequest) -> ReviewDecision:
    dur = f"{req.duration_seconds:.1f}s" if req.duration_seconds else "unknown"
    print(
        "\n"
        f"── Review generation {req.generation} "
        f"({req.render_attempts} render attempt(s), {dur}) ──\n"
        f"  video      : {req.video_path}\n"
        f"  transcript : {req.transcript_path}\n"
        f"  script     : {req.script_path}\n"
        "Open the video, then decide.",
        flush=True,
    )
    while True:
        ans = input("Approve? [y]es / [r]eject+note / [q]uit: ").strip().lower()
        if ans in {"y", "yes"}:
            return ReviewDecision(approved=True)
        if ans in {"q", "quit"}:
            raise SystemExit("aborted at review")
        if ans in {"r", "reject", "n", "no"}:
            note = input("Rejection note (fed into the next generation): ").strip()
            return ReviewDecision(approved=False, note=note)
        print("  please answer y, r, or q")


def _auto_reviewer(req: ReviewRequest) -> ReviewDecision:
    print(
        f"--yes: auto-approving generation {req.generation} "
        f"({req.render_attempts} render attempt(s)).",
        flush=True,
    )
    return ReviewDecision(approved=True)


def _rerender(args: argparse.Namespace) -> int:
    """No LLM at all: render the committed ``scenes/<slug>/scene.py`` and refresh
    the ``.mp4``. The existing ``.vtt`` is left untouched — re-run without
    ``--rerender`` (or upload a hand-edited transcript) if the captions need to
    change too."""
    scene = scene_store.load(args.slug)
    scene_name = args.scene_name or scriptgen.scene_name_for(args.slug)
    quality = args.quality or DEFAULT_RENDER_QUALITY

    video_path = render_once(
        scene.script_path,
        scene_name,
        slug=args.slug,
        out_dir=Path(args.out),
        quality=quality,
    )
    print(
        f"rendered -> {video_path}\n"
        "(transcript unchanged — --rerender does not call the LLM)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="author.py", description=__doc__)
    parser.add_argument("--slug", required=True, help="kebab-case id; keys scenes/<slug>/ and the uploaded Animation")
    parser.add_argument("--idea", help="the plain-language idea string")
    parser.add_argument("--idea-file", help="read the idea from this file instead")
    parser.add_argument("--out", default=str(DEFAULT_OUT_DIR), help=f"artifact dir (default {DEFAULT_OUT_DIR})")
    parser.add_argument("--scene-name", help="Scene subclass name (default derived from the slug)")
    parser.add_argument("--quality", choices=list(RENDER_QUALITIES), help="manim quality flag (default from env / 'm')")
    parser.add_argument("--retries", type=int, help="render-traceback feedback retries (default from env / 3)")
    parser.add_argument("--max-regenerations", type=int, default=3, help="reviewer rejections tolerated before giving up")
    parser.add_argument("--from-scene", action="store_true", help="seed from the committed scenes/<slug>/scene.py")
    parser.add_argument("--reject-note", help="seed rejection note; implies --from-scene")
    parser.add_argument("--rerender", action="store_true", help="no LLM: just render the committed scene.py")
    parser.add_argument("--yes", action="store_true", help="auto-approve every generation (non-interactive)")
    args = parser.parse_args(argv)

    try:
        scene_store.validate_slug(args.slug)
        if args.rerender:
            return _rerender(args)
        return _author(args)
    except scene_store.SceneStoreError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except RenderUnavailable as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 1


def _author(args: argparse.Namespace) -> int:
    """The LLM-driven path: draft -> render (retries) -> transcript -> review."""
    try:
        config = load_config()
        config.require_api_key()
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    if args.retries is not None:
        config = dataclasses.replace(config, render_retries=args.retries)
    if args.quality is not None:
        config = dataclasses.replace(config, render_quality=args.quality)

    idea = _read_idea(args)
    seed_from = args.from_scene or bool(args.reject_note)
    seed_script = scene_store.load(args.slug).script if seed_from and scene_store.exists(args.slug) else None

    reviewer = _auto_reviewer if args.yes else _interactive_reviewer

    try:
        artifacts = author_animation(
            get_client(config),
            config,
            idea=idea,
            slug=args.slug,
            out_dir=Path(args.out),
            reviewer=reviewer,
            scene_name=args.scene_name,
            max_regenerations=args.max_regenerations,
            seed_script=seed_script,
            seed_rejection_note=args.reject_note,
        )
    except (PipelineError, AnimLLMError, RenderUnavailable, scriptgen.ScriptGenerationError) as exc:
        print(f"\nfailed: {exc}", file=sys.stderr)
        return 1

    print(
        "\n✓ approved.\n"
        f"  upload these through the ContentAdmin animation screen (slug '{artifacts.slug}'):\n"
        f"    video      {artifacts.video_path}\n"
        f"    transcript {artifacts.transcript_path}\n"
        f"  commit the source so it can be re-rendered:\n"
        f"    git add {artifacts.scene_dir.as_posix()}\n"
        f"  ({artifacts.generations} generation(s), "
        f"{artifacts.render_attempts} render attempt(s) in the last one)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
