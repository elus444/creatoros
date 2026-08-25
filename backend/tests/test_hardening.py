"""M7 hardening: rate limits, health probes, safe errors, production guards."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings


def test_health_live_and_ready(client: TestClient) -> None:
    live = client.get("/api/v1/health/live")
    assert live.status_code == 200
    assert live.json()["status"] == "ok"

    ready = client.get("/api/v1/health/ready")
    assert ready.status_code == 200
    assert ready.json()["database"] == "ok"
    assert ready.json()["redis"] == "ok"

    root = client.get("/health")
    assert root.status_code == 200
    assert root.json()["status"] == "ok"


def test_unhandled_errors_do_not_leak_stack(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.main import app
    from app.services.project_service import ProjectService

    monkeypatch.setattr(
        ProjectService,
        "list_for_user",
        lambda self, user: (_ for _ in ()).throw(
            RuntimeError("internal db dsn leaked")
        ),
    )
    # TestClient re-raises server exceptions by default; disable to assert
    # the production-safe JSON body clients actually receive.
    with TestClient(app, raise_server_exceptions=False) as leak_client:
        response = leak_client.get("/api/v1/projects", headers=auth_headers)
    assert response.status_code == 500
    body = response.json()
    assert "internal db" not in str(body).lower()
    assert body["detail"] == "An unexpected error occurred. Please try again."


def test_rate_limit_on_expensive_endpoint(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_user_max", 2)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)

    project = client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"name": "RL", "niche": "test"},
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    # Collect is rate-limited; stub collect to avoid network work.
    from app.services.trend_service import TrendService

    async def fake_collect(self, project, query=None):
        return [], 0, [], []

    monkeypatch.setattr(TrendService, "collect", fake_collect)

    codes = []
    for _ in range(3):
        codes.append(
            client.post(
                f"/api/v1/projects/{project_id}/trends/collect",
                headers=auth_headers,
                json={},
            ).status_code
        )
    assert codes[:2] == [200, 200]
    assert codes[2] == 429


def test_rate_limit_on_analytics_coach(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_user_max", 2)

    project = client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"name": "Analytics Rate Limit", "niche": "test"},
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    codes = [
        client.post(
            f"/api/v1/analytics/projects/{project_id}/coach", headers=auth_headers
        ).status_code
        for _ in range(3)
    ]
    assert codes == [200, 200, 429]


def test_production_rejects_weak_jwt(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings(
            environment="production",
            jwt_secret="change-me-to-a-long-random-secret-in-production",
            cors_origins="https://app.example.com",
        ).validate_for_runtime()


def test_production_rejects_wildcard_cors() -> None:
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings(
            environment="production",
            jwt_secret="a" * 40,
            cors_origins="*",
        ).validate_for_runtime()


def test_production_rejects_local_storage_backend() -> None:
    """local serves every video from an unauthenticated /media mount — any
    user's video URL would be publicly guessable with no per-user access
    control, so production must use a backend (supabase) that issues
    signed, owner-scoped URLs instead.
    """
    with pytest.raises(ValueError, match="STORAGE_BACKEND"):
        Settings(
            environment="production",
            jwt_secret="a" * 40,
            cors_origins="https://app.example.com",
            storage_backend="local",
        ).validate_for_runtime()


def test_production_allows_supabase_storage_backend() -> None:
    # Should not raise: supabase is the production-safe backend.
    Settings(
        environment="production",
        jwt_secret="a" * 40,
        cors_origins="https://app.example.com",
        storage_backend="supabase",
    ).validate_for_runtime()


def _fake_request(*, client_host: str, xff: str | None) -> "Request":
    from starlette.requests import Request

    headers = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode("utf-8")))
    scope = {
        "type": "http",
        "headers": headers,
        "client": (client_host, 12345),
        "method": "GET",
        "path": "/",
    }
    return Request(scope)


def test_rate_limit_ignores_spoofed_xff_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """With TRUSTED_PROXY_HOPS=0 (default), a client-supplied
    X-Forwarded-For must never influence the rate-limit identity — otherwise
    any client can dodge limits by sending a fresh fake IP on every request.
    """
    from app.core.config import get_settings
    from app.core.rate_limit import identity_for_request

    get_settings.cache_clear()
    try:
        request = _fake_request(client_host="203.0.113.9", xff="1.2.3.4")
        assert identity_for_request(request) == "ip:203.0.113.9"
    finally:
        get_settings.cache_clear()


def test_rate_limit_trusts_configured_proxy_hop(monkeypatch: pytest.MonkeyPatch) -> None:
    """With TRUSTED_PROXY_HOPS=1, the identity comes from the hop our own
    proxy appended (rightmost), not whatever the client put at the front
    of the chain.
    """
    from app.core import rate_limit as rate_limit_module
    from app.core.config import Settings, get_settings

    monkeypatch.setattr(
        rate_limit_module,
        "get_settings",
        lambda: Settings(trusted_proxy_hops=1),
    )
    # Client-spoofed entry first, then the real hop our trusted proxy added.
    request = _fake_request(client_host="10.0.0.5", xff="1.2.3.4, 203.0.113.9")
    assert rate_limit_module.identity_for_request(request) == "ip:203.0.113.9"


def test_invalid_login_and_unauthorized(client: TestClient) -> None:
    bad = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "wrong-password"},
    )
    assert bad.status_code in (401, 400)
    assert client.get("/api/v1/projects").status_code == 401
    assert (
        client.get(
            "/api/v1/projects/00000000-0000-0000-0000-000000000001"
        ).status_code
        == 401
    )
