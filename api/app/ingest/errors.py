"""The one exception the ingest raises for author-facing problems."""

from __future__ import annotations


class ManifestError(Exception):
    """A manifest is malformed or inconsistent — a bad reference, an unknown
    question type, a missing required field, an unreadable or empty lecture
    file, a duplicate slug.

    The message is written for a content admin and is safe to print or return
    from an API. When this is raised the database is untouched: the manifest is
    parsed and fully validated before the ingest writes anything.
    """
