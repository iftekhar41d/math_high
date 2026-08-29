"""`python -m app.ingest [MANIFEST]` — load course content into the database.

Thin wrapper over `app.ingest.load_and_ingest`. Run it from inside `api/` (like
every command in this project). The manifest path defaults to
`content/manifest.yaml`.

Safe to re-run: every entity is upserted by its slug, so a second run over the
same content changes nothing. A malformed manifest prints the reason to stderr,
exits non-zero, and writes nothing.
"""

from __future__ import annotations

import argparse
import sys

from app.database import SessionLocal
from app.ingest import ManifestError, load_and_ingest

DEFAULT_MANIFEST = "content/manifest.yaml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.ingest",
        description="Load a course manifest into the database (idempotent).",
    )
    parser.add_argument(
        "manifest",
        nargs="?",
        default=DEFAULT_MANIFEST,
        help=f"path to the manifest YAML (default: {DEFAULT_MANIFEST})",
    )
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        summary = load_and_ingest(db, args.manifest)
    except ManifestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print(f"ingested {args.manifest}:")
    for kind, total in summary.total.items():
        print(f"  {kind:12} {total:>4}   ({summary.created[kind]} new)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
