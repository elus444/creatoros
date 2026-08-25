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
from app.services import automation_service as automation_service_module


class FakeRedis:
    """Minimal in-memory stand-in for the subset of Redis commands we use."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._lists: dict[str, list[str]] = {}

    def setex(self, key: str, _time: int, value: str) -> None:
        self._store[key] = value

    def set(self, key: str, value: str, ex: int | None = None, nx: bool = False) -> bool:
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def exists(self, key: str) -> int:
        return 1 if key in self._store else 0

    def lpush(self, key: str, value: str) -> int:
        self._lists.setdefault(key, []).insert(0, value)
        return len(self._lists[key])

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        values = self._lists.get(key, [])
        if end == -1:
            return values[start:]
        return values[start : end + 1]

    def ltrim(self, key: str, start: int, end: int) -> None:
        values = self._lists.get(key, [])
        self._lists[key] = values[start : end + 1]

    def expire(self, key: str, _time: int) -> None:
        return None

    def ttl(self, key: str) -> int:
        # This fake doesn't track per-key expiry, so there's no real TTL to
        # report; callers treat a non-positive value as "unknown".
        return -1 if key in self._store else -2

    def incr(self, key: str) -> int:
        current = int(self._store.get(key, "0"))
        current += 1
        self._store[key] = str(current)
        return current

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self._store:
                del self._store[key]
                removed += 1
        return removed

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
    from app.core import rate_limit as rate_limit_module

    monkeypatch.setattr(rate_limit_module, "redis_client", fake_redis)
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
    # Background automation jobs must use the same in-memory DB as the request.
    monkeypatch.setattr(automation_service_module, "SessionLocal", testing_session_local)

    from app.core.config import get_settings

    # Keep API tests off the live Replicate path unless a test fakes the provider.
    monkeypatch.setenv("VIDEO_GENERATION_PROVIDER", "none")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    monkeypatch.setattr(settings, "n8n_webhook_secret", "test-automation-secret")
    monkeypatch.setattr(settings, "video_generation_provider", "none")
    monkeypatch.setattr(settings, "replicate_api_token", None)
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "supabase_secret_key", None)
    monkeypatch.setattr(settings, "supabase_key", None)

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


@pytest.fixture()
def automation_headers() -> dict[str, str]:
    return {"X-Automation-Secret": "test-automation-secret"}
