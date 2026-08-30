"""Render a Manim scene by shelling out to the ``manim`` CLI.

We invoke the CLI as a subprocess rather than ``import manim`` so this package
imports cleanly on a machine without Manim installed (the smoke test and the
pure seams do not need it). A failed render returns its captured output as
``traceback`` for the pipeline to feed back to the LLM.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_TRACEBACK_TAIL_CHARS = 6000


class RenderUnavailable(RuntimeError):
    """The ``manim`` CLI is not on PATH — install ``tools/anim/requirements.txt``."""


@dataclass(frozen=True)
class RenderResult:
    ok: bool
    video_path: Path | None
    log: str
    traceback: str | None  # populated iff not ok


def manim_available() -> bool:
    return shutil.which("manim") is not None


def _newest_mp4(media_dir: Path) -> Path | None:
    """The freshest fully-rendered scene video.

    Manim writes finished scenes under ``<media_dir>/videos/**`` and scratch
    chunks under ``partial_movie_files/`` (also ``.mp4``) — those are skipped so a
    retry never picks up a half-render.
    """
    candidates = [
        p
        for p in (media_dir / "videos").rglob("*.mp4")
        if "partial_movie_files" not in p.parts
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def render_scene(
    script_path: Path,
    scene_name: str,
    *,
    out_dir: Path,
    quality: str = "m",
    timeout_seconds: float = 600.0,
) -> RenderResult:
    """Run ``manim render`` for ``scene_name`` in ``script_path``.

    Manim's media tree is written under ``out_dir/media``; the produced ``.mp4``
    is located by mtime and returned in ``video_path`` on success.
    """
    if not manim_available():
        raise RenderUnavailable(
            "`manim` was not found on PATH. Create the toolchain venv and "
            "`pip install -r tools/anim/requirements.txt` (plus a LaTeX distro "
            "and ffmpeg)."
        )
    media_dir = out_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "manim",
        "render",
        f"-q{quality}",
        "--format",
        "mp4",
        "--media_dir",
        str(media_dir),
        "--output_file",
        f"{script_path.stem}",
        str(script_path),
        scene_name,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(script_path.parent),
        )
    except subprocess.TimeoutExpired as exc:
        return RenderResult(
            ok=False,
            video_path=None,
            log=(exc.stdout or "") + (exc.stderr or ""),
            traceback=f"manim render timed out after {timeout_seconds:.0f}s",
        )

    log = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return RenderResult(
            ok=False,
            video_path=None,
            log=log,
            traceback=log[-_TRACEBACK_TAIL_CHARS:].strip()
            or f"manim exited {proc.returncode} with no output",
        )

    video = _newest_mp4(media_dir)
    if video is None:
        return RenderResult(
            ok=False,
            video_path=None,
            log=log,
            traceback="manim reported success but no .mp4 was produced:\n"
            + log[-_TRACEBACK_TAIL_CHARS:],
        )
    return RenderResult(ok=True, video_path=video, log=log, traceback=None)


def probe_duration_seconds(video_path: Path) -> float | None:
    """Best-effort duration via ``ffprobe`` (bundled with ffmpeg). ``None`` if
    ffprobe is missing or the probe fails."""
    if shutil.which("ffprobe") is None:
        return None
    try:
        out = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nokey=1",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return float(out.stdout.strip())
    except (ValueError, OSError, subprocess.SubprocessError):
        return None
