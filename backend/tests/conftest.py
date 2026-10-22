"""Tests run against a real Postgres database named `*_test`, created if it is missing."""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.database import Base, create_tables, get_db
from app.main import app
from app.seed import load_seed, read_seed

TEST_URL = make_url(
    os.environ.get(
        "TEST_DATABASE_URL", "postgresql+psycopg://menu:menu@localhost:5434/restaurant_test"
    )
)
assert TEST_URL.database and TEST_URL.database.endswith("_test"), "tests need a *_test database"


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    admin = create_engine(TEST_URL.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_URL.database}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_URL.database}"'))
    admin.dispose()
    eng = create_engine(TEST_URL)
    Base.metadata.drop_all(eng)  # always start from a clean test database
    create_tables(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    """The app talking to the test database, loaded with the seed."""
    with Session(engine) as session:
        load_seed(session, read_seed())

    def test_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = test_session
    yield TestClient(app)
    app.dependency_overrides.clear()
