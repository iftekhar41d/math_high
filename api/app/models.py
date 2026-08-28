"""SQLAlchemy models.

Empty in the walking skeleton — the placeholder `Item` scaffold has been
removed and the Phase 1 domain tables (`User`, `YearLevel`, `Subject`, `Unit`,
`Topic`, ...) arrive with their own tickets. Alembic is the schema source of
truth (`migrations/`); this module is imported by `migrations/env.py` so that
`--autogenerate` sees every model's metadata.
"""

from app.database import Base  # noqa: F401  (re-exported for migrations/env.py)
