"""The media-storage boundary — `save()` / `get_url()` over lecture media.

Every read or write of a lecture image goes through this seam so that moving
off local disk (to S3/R2) later is a single class swap, not a sweep through the
codebase. Phase 1 has one implementation: files under a local directory that
nginx serves directly at ``/media/`` (`deploy/nginx.conf`), bypassing the API.

Provided as a FastAPI dependency (`get_media_storage`), same pattern as the
`Clock` / `EmailSender` / `MentisQLLMClient` adapters.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import BinaryIO

# Public URL prefix. Keep in step with the nginx `location /media/` block and
# the `MEDIA_URL_PREFIX` any content references use in Markdown.
MEDIA_URL_PREFIX = "/media"


class MediaStorage:
    """Interface. A `key` is a relative POSIX-style path within the store
    (e.g. ``"topics/integers/number-line.png"``)."""

    def save(self, key: str, source: BinaryIO) -> str:  # pragma: no cover
        """Persist `source`'s bytes at `key`; return the public URL for it."""
        raise NotImplementedError

    def get_url(self, key: str) -> str:  # pragma: no cover - abstract
        """The public URL a browser fetches `key` from."""
        raise NotImplementedError


def _safe_key(key: str) -> str:
    """Normalise `key` to a relative POSIX path, rejecting anything that would
    escape the store (absolute paths, `..` traversal)."""
    cleaned = os.path.normpath(key).replace("\\", "/").lstrip("/")
    if cleaned == ".." or cleaned.startswith("../") or not cleaned or cleaned == ".":
        raise ValueError(f"unsafe media key: {key!r}")
    return cleaned


class LocalMediaStorage(MediaStorage):
    """Files under `root`; URLs are `MEDIA_URL_PREFIX` + `/` + key."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self._root = Path(root)

    def save(self, key: str, source: BinaryIO) -> str:
        safe = _safe_key(key)
        dest = self._root / safe
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as fh:
            shutil.copyfileobj(source, fh)
        return f"{MEDIA_URL_PREFIX}/{safe}"

    def get_url(self, key: str) -> str:
        return f"{MEDIA_URL_PREFIX}/{_safe_key(key)}"


def get_media_storage() -> MediaStorage:
    """FastAPI dependency. `MEDIA_ROOT` defaults to `api/data/media` (resolved
    from the CWD, same as `DATABASE_URL`); override with a real backend in a
    future ticket."""
    return LocalMediaStorage(os.getenv("MEDIA_ROOT", "./data/media"))
