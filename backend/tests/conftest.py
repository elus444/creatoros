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
        yield test_client

    app.dependency_overrides.clear()
