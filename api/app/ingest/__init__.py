"""Seed-ingest core: parse + validate a course manifest, then upsert it by slug.

The public surface here is the contract a future admin content-upload UI will
call; `python -m app.ingest` (see `__main__.py`) is only a thin CLI over it.

* `parse_manifest(data, lecture_loader=...)` / `load_manifest_file(path)` —
  validate, raising `ManifestError` for anything an author can fix.
* `ingest_manifest(db, manifest)` / `load_and_ingest(db, path)` — upsert, in
  one transaction, idempotently.
"""

from app.ingest.errors import ManifestError
from app.ingest.ingest import IngestSummary, ingest_manifest, load_and_ingest
from app.ingest.manifest import (
    Manifest,
    assert_manifest_consistent,
    load_manifest_file,
    parse_manifest,
)

__all__ = [
    "ManifestError",
    "IngestSummary",
    "ingest_manifest",
    "load_and_ingest",
    "Manifest",
    "assert_manifest_consistent",
    "load_manifest_file",
    "parse_manifest",
]
