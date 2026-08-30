"""Toolchain configuration — read once from the environment.

The only required var is ``OPENROUTER_API_KEY`` (reused from the API's env).
``ANIM_LLM_MODEL`` is this tool's *own* model setting, separate from the API's
``OPENROUTER_MODEL``; everything else has a working default. If a ``.env`` file
sits next to the package and ``python-dotenv`` is installed, it is loaded first —
but exported shell vars always win.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent  # tools/anim/
SCENES_DIR = PACKAGE_ROOT / "scenes"
DEFAULT_OUT_DIR = PACKAGE_ROOT / "out"

DEFAULT_MODEL = "openai/gpt-4o"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_RENDER_RETRIES = 3
RENDER_QUALITIES = ("l", "m", "h", "p", "k")  # manim -q flag; m == 720p30
DEFAULT_RENDER_QUALITY = "m"
DEFAULT_LLM_TIMEOUT_SECONDS = 120.0


def _load_dotenv() -> None:
    """Best-effort: load ``tools/anim/.env`` if python-dotenv is present.

    The toolchain works fine without it (export the vars instead); this is a
    convenience for local runs and never overrides an already-set var.
    """
    env_path = PACKAGE_ROOT / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv  # type: ignore
    except ModuleNotFoundError:
        return
    load_dotenv(env_path, override=False)


@dataclass(frozen=True)
class Config:
    openrouter_api_key: str
    model: str
    base_url: str
    render_retries: int
    render_quality: str
    llm_timeout_seconds: float

    @property
    def has_api_key(self) -> bool:
        return bool(self.openrouter_api_key)

    def require_api_key(self) -> str:
        if not self.openrouter_api_key:
            raise ConfigError(
                "OPENROUTER_API_KEY is not set. Export it or put it in "
                "tools/anim/.env (see tools/anim/.env.example). The toolchain "
                "reuses the same key as the API."
            )
        return self.openrouter_api_key


class ConfigError(RuntimeError):
    """A required setting is missing or malformed."""


def _num_env(name: str, default, cast):
    """Read ``name`` as ``cast`` (``int`` / ``float``), falling back to
    ``default`` when unset. A non-numeric value is a :class:`ConfigError`."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return cast(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a {cast.__name__}, got {raw!r}") from exc


def load_config() -> Config:
    _load_dotenv()
    quality = (os.getenv("ANIM_RENDER_QUALITY") or DEFAULT_RENDER_QUALITY).strip().lower()
    if quality not in RENDER_QUALITIES:
        raise ConfigError(
            f"ANIM_RENDER_QUALITY must be one of {'/'.join(RENDER_QUALITIES)}, "
            f"got {quality!r}"
        )
    return Config(
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
        model=(os.getenv("ANIM_LLM_MODEL") or DEFAULT_MODEL).strip(),
        base_url=(os.getenv("OPENROUTER_BASE_URL") or DEFAULT_BASE_URL).strip(),
        render_retries=_num_env("ANIM_RENDER_RETRIES", DEFAULT_RENDER_RETRIES, int),
        render_quality=quality,
        llm_timeout_seconds=_num_env(
            "ANIM_LLM_TIMEOUT_SECONDS", DEFAULT_LLM_TIMEOUT_SECONDS, float
        ),
    )
