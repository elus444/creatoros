"""Shared pytest fixtures for the creatoros backend test suite.

Every milestone's test module (test_trends.py, test_content.py, ...) should
reuse the `client` fixture below instead of redefining its own in-memory
database / fake Redis setup.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core import redis as redis_module
from app.core.database import Base, get_db
from app.main import app


class FakeRedis:
    """Minimal in-memory stand-in for the subset of Redis commands we use."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def setex(self, key: str, _time: int, value: str) -> None:
        self._store[key] = value

    def exists(self, key: str) -> int:
        return 1 if key in self._store else 0

    def ping(self) -> bool:
        return True


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    """A TestClient wired to an isolated in-memory SQLite DB and fake Redis.

    Import side effect: importing app.main triggers app.models.__init__ which
    registers every model with Base.metadata, so new tables from later
    milestones are created automatically as long as they're added there.
    """
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    fake_redis = FakeRedis()
    monkeypatch.setattr(redis_module, "redis_client", fake_redis)
    monkeypatch.setattr(
        redis_module,
        "blacklist_token",
        lambda jti, expires: fake_redis.setex(f"auth:blacklist:{jti}", expires, "1"),
    )
    monkeypatch.setattr(
        redis_module,
        "is_token_blacklisted",
        lambda jti: fake_redis.exists(f"auth:blacklist:{jti}") == 1,
    )
    monkeypatch.setattr(redis_module, "ping_redis", lambda: True)

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        # Exposed so tests can open their own session to assert on rows the
        # API doesn't expose directly (e.g. agent_runs), without duplicating
        # this whole engine/session setup in every test module.
        test_client.session_local = testing_session_local
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _stub_google_trends_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevents the test suite from making real network calls to Google Trends.

    Applied to every test automatically. Tests that specifically exercise
    `GoogleTrendsCollector` re-patch `collect` (or the underlying HTTP call)
    themselves after this fixture has run.
    """
    from app.services.collectors.google_trends_collector import GoogleTrendsCollector

    async def _empty_collect(self, query: str, limit: int = 10) -> list:
        return []

    monkeypatch.setattr(GoogleTrendsCollector, "collect", _empty_collect)


@pytest.fixture()
def auth_headers(client: TestClient) -> dict[str, str]:
    """Registers a fresh user and returns an `Authorization` header for it."""
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "creator@example.com", "password": "securepass1"},
    )
    assert response.status_code == 201
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
