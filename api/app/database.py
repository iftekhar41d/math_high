import os

from sqlalchemy import create_engine
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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
