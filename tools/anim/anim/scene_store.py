"""The committed source for an animation: ``scenes/<slug>/``.

Two files per slug, both tracked in git so a render is reproducible and the
script is hand-editable:

- ``idea.txt``   — the plain-language prompt the animation was authored from
- ``scene.py``   — the latest Manim script: the one that rendered / was approved,
  or on a failed run the last attempt, left in place for a hand-edit

The ``.mp4`` + ``.vtt`` do NOT live here — they are uploaded through the
ContentAdmin screen (ticket 11).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import SCENES_DIR

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class SceneStoreError(RuntimeError):
    """The slug is malformed or no scene is stored for it."""


def validate_slug(slug: str) -> str:
    if not _SLUG_RE.match(slug):
        raise SceneStoreError(
            f"slug {slug!r} must be kebab-case (lowercase letters, digits, "
            "single hyphens) — it keys the scene dir and the uploaded Animation."
        )
    return slug


@dataclass(frozen=True)
class Scene:
    slug: str
    idea: str
    script: str
    directory: Path

    @property
    def script_path(self) -> Path:
        return self.directory / "scene.py"

    @property
    def idea_path(self) -> Path:
        return self.directory / "idea.txt"


def scene_dir(slug: str) -> Path:
    return SCENES_DIR / validate_slug(slug)


def script_path(slug: str) -> Path:
    return scene_dir(slug) / "scene.py"


def exists(slug: str) -> bool:
    return script_path(slug).is_file()


def load(slug: str) -> Scene:
    d = scene_dir(slug)
    if not (d / "scene.py").is_file():
        raise SceneStoreError(f"no scene at {d / 'scene.py'}")
    idea_path = d / "idea.txt"
    idea = idea_path.read_text(encoding="utf-8") if idea_path.is_file() else ""
    return Scene(
        slug=slug,
        idea=idea,
        script=(d / "scene.py").read_text(encoding="utf-8"),
        directory=d,
    )


def save(slug: str, *, idea: str, script: str) -> Scene:
    """Write / overwrite ``idea.txt`` + ``scene.py`` for ``slug``."""
    d = scene_dir(slug)
    d.mkdir(parents=True, exist_ok=True)
    idea_text = idea.strip() + "\n"
    script_text = script if script.endswith("\n") else script + "\n"
    (d / "idea.txt").write_text(idea_text, encoding="utf-8")
    (d / "scene.py").write_text(script_text, encoding="utf-8")
    return Scene(slug=slug, idea=idea_text, script=script_text, directory=d)
