"""
Shared pytest fixtures for API tests.

Why in-memory SQLite instead of spinning up a real Postgres for tests: the
generic `Uuid` type (see db/models.py's docstring) makes our models
portable across dialects, so tests get a real, fast, disposable database
per test without any Docker/Postgres dependency in CI. `StaticPool` is
required here — SQLite's `:memory:` database only exists for the lifetime
of a single connection, and StaticPool ensures every session in a test
reuses the same underlying connection instead of getting a fresh (empty)
in-memory DB each time.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.models import Base
from src.db.session import get_db
from src.main import app


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_engine):
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(client):
    """Registers a throwaway user and returns ready-to-use Authorization headers."""
    client.post(
        "/auth/register", json={"email": "test@example.com", "password": "supersecret123"}
    )
    response = client.post(
        "/auth/token",
        data={"username": "test@example.com", "password": "supersecret123"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
