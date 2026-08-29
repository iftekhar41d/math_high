"""`alembic upgrade head` must build the schema on a fresh SQLite database."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

API_DIR = Path(__file__).resolve().parents[1]


def _alembic_config(db_url: str) -> Config:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_upgrade_head_on_a_fresh_database(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path / 'fresh.db'}"
    # env.py also reads DATABASE_URL; keep it pointed at the throwaway file.
    monkeypatch.setenv("DATABASE_URL", db_url)

    command.upgrade(_alembic_config(db_url), "head")

    engine = create_engine(db_url)
    try:
        tables = set(inspect(engine).get_table_names())
        assert "alembic_version" in tables
        # A later migration's table, to catch a broken revision chain.
        assert "performance_snapshots" in tables
        with engine.connect() as conn:
            version = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
        assert version  # a concrete head revision was stamped
    finally:
        engine.dispose()


def test_downgrade_to_base_then_upgrade_again(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path / 'rev.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    cfg = _alembic_config(db_url)

    # A full round trip must not raise: head -> base -> head.
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            count = conn.execute(
                text("SELECT count(*) FROM alembic_version")
            ).scalar()
        assert count == 1
    finally:
        engine.dispose()
