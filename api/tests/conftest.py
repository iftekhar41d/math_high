"""Test harness: FastAPI TestClient + ephemeral SQLite + boundary fakes.

Every test gets a fresh in-memory database and the three external-boundary
adapters (`Clock`, `EmailSender`, `MentisQLLMClient`) swapped for the fakes in
`fakes.py` via dependency overrides. Tests assert on HTTP responses and
persisted state — the observable behaviour of the API — not internals.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.clock import get_clock
from app.database import Base, get_db
from app.email_sender import get_email_sender
from app.main import app
from app.mentisq.llm_client import get_llm_client
from tests.fakes import FakeClock, FakeEmailSender, FakeMentisQLLMClient


@pytest.fixture
def db_engine():
    """A fresh in-memory SQLite DB per test, shared across connections.

    Schema is applied with `create_all` for speed; it is equivalent to
    `alembic upgrade head` here (no models yet). `test_migrations.py` covers the
    Alembic path itself.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def fake_email() -> FakeEmailSender:
    return FakeEmailSender()


@pytest.fixture
def fake_llm() -> FakeMentisQLLMClient:
    return FakeMentisQLLMClient()


@pytest.fixture
def client(db_engine, fake_clock, fake_email, fake_llm):
    Session = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_clock] = lambda: fake_clock
    app.dependency_overrides[get_email_sender] = lambda: fake_email
    app.dependency_overrides[get_llm_client] = lambda: fake_llm
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
