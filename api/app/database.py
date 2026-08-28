import os
from datetime import datetime, timezone

from sqlalchemy import DateTime, TypeDecorator, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Default points at the local SQLite file, resolved relative to the CWD (run
# from inside api/). Swap this env var to a postgresql+psycopg://... URL later;
# no code changes needed. `migrations/env.py` reads the same env var + default.
DEFAULT_DATABASE_URL = "sqlite:///./data/app.db"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class UtcDateTime(TypeDecorator):
    """A timestamp column that always hands app code a tz-aware UTC `datetime`.

    SQLite's `DateTime` silently drops `tzinfo`, which then blows up any
    comparison against the tz-aware time the `Clock` returns. This normalises
    both directions (aware-UTC in, aware-UTC out) and is a no-op cast on
    Postgres, where the underlying `timestamptz` already round-trips correctly.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
