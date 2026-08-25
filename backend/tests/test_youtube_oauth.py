"""YouTube OAuth connect / status / disconnect — tokens never leave the server."""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.models.user import User
from app.models.youtube_credential import YouTubeCredential
from app.services.youtube_service import YouTubeService, decrypt_secret


def _enable_oauth(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "youtube_oauth_client_id", "test-client-id")
    monkeypatch.setattr(settings, "youtube_oauth_client_secret", "test-client-secret")
    monkeypatch.setattr(
        settings,
        "youtube_oauth_redirect_uri",
        "http://localhost:8000/api/v1/youtube/oauth/callback",
    )
    monkeypatch.setattr(settings, "frontend_url", "http://localhost:3000")


def _user_id(client: TestClient, auth_headers: dict[str, str]):
    me = client.get("http://testserver/api/v1/auth/me", headers=auth_headers)
    assert me.status_code == 200
    return me.json()["id"]


def test_oauth_start_fails_when_unconfigured(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get("/api/v1/youtube/oauth/start", headers=auth_headers)
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"].lower()


def test_oauth_start_returns_google_url_and_stores_state(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_oauth(monkeypatch)
    response = client.get("/api/v1/youtube/oauth/start", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["authorization_url"].startswith(
        "https://accounts.google.com/o/oauth2/v2/auth?"
    )
    parsed = urlparse(data["authorization_url"])
    params = parse_qs(parsed.query)
    assert params["client_id"] == ["test-client-id"]
    assert params["response_type"] == ["code"]
    assert params["access_type"] == ["offline"]
    assert params["prompt"] == ["consent"]
    assert params["include_granted_scopes"] == ["true"]
    assert params["scope"] == ["https://www.googleapis.com/auth/youtube.upload"]
    assert "scope=https://www.googleapis.com/auth/youtube.upload" in data["authorization_url"]
    assert data["state"]
    assert "access_token" not in data


def test_callback_cancellation_redirects_to_settings(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_oauth(monkeypatch)
    response = client.get(
        "/api/v1/youtube/oauth/callback",
        params={"error": "access_denied", "state": "abc"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "http://localhost:3000/settings?youtube=cancelled"


def test_complete_oauth_flow_saves_encrypted_tokens_and_channel(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_oauth(monkeypatch)

    def fake_token_request(self, data: dict) -> dict:
        assert data["grant_type"] == "authorization_code"
        assert data["code"] == "live-code"
        return {
            "access_token": "ya29.access-secret",
            "refresh_token": "1//refresh-secret",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

    def fake_fetch_channel(self, access_token: str):
        assert access_token == "ya29.access-secret"
        return (
            "UC123channel",
            "Kids Counting Club",
            "https://yt.example/avatar.jpg",
        )

    monkeypatch.setattr(YouTubeService, "_google_token_request", fake_token_request)
    monkeypatch.setattr(YouTubeService, "_fetch_channel", fake_fetch_channel)

    start = client.get("/api/v1/youtube/oauth/start", headers=auth_headers).json()
    callback = client.get(
        "/api/v1/youtube/oauth/callback",
        params={"code": "live-code", "state": start["state"]},
        follow_redirects=False,
    )
    assert callback.status_code == 302
    assert callback.headers["location"] == (
        "http://localhost:3000/settings?youtube=connected"
    )
    assert "ya29" not in callback.headers["location"]
    assert "refresh" not in callback.headers["location"].lower()

    status = client.get("/api/v1/youtube/status", headers=auth_headers)
    assert status.status_code == 200
    body = status.json()
    assert body["connected"] is True
    assert body["needs_reconnect"] is False
    assert body["channel_id"] == "UC123channel"
    assert body["channel_title"] == "Kids Counting Club"
    assert body["channel_thumbnail_url"] == "https://yt.example/avatar.jpg"
    assert "access_token" not in body
    assert "refresh_token" not in body
    assert "access_token_encrypted" not in body

    db = client.session_local()
    try:
        row = db.query(YouTubeCredential).one()
        assert str(row.user_id) == _user_id(client, auth_headers)
        assert row.access_token_encrypted != "ya29.access-secret"
        secret = get_settings().jwt_secret
        assert decrypt_secret(row.access_token_encrypted, secret) == "ya29.access-secret"
        assert decrypt_secret(row.refresh_token_encrypted, secret) == "1//refresh-secret"
    finally:
        db.close()


def test_callback_rejects_unknown_state(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_oauth(monkeypatch)
    response = client.get(
        "/api/v1/youtube/oauth/callback",
        params={"code": "x", "state": "not-a-real-state"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "invalid_state" in response.headers["location"]


def test_disconnect_removes_credential(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_oauth(monkeypatch)
    db = client.session_local()
    try:
        user = db.query(User).one()
        YouTubeService(db).store_tokens_for_tests(
            user,
            access_token="access",
            refresh_token="refresh",
            channel_id="UCabc",
            channel_title="My Channel",
        )
    finally:
        db.close()

    monkeypatch.setattr(YouTubeService, "_revoke_google_token", lambda self, token: None)
    monkeypatch.setattr(
        YouTubeService,
        "_google_token_request",
        lambda self, data: (_ for _ in ()).throw(AssertionError("no refresh")),
    )

    before = client.get("/api/v1/youtube/status", headers=auth_headers).json()
    assert before["connected"] is True

    gone = client.delete("/api/v1/youtube/connection", headers=auth_headers)
    assert gone.status_code == 204

    after = client.get("/api/v1/youtube/status", headers=auth_headers).json()
    assert after["connected"] is False
    assert after["channel_id"] is None


def test_expired_token_without_refresh_asks_to_reconnect(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_oauth(monkeypatch)
    db = client.session_local()
    try:
        user = db.query(User).one()
        row = YouTubeService(db).store_tokens_for_tests(
            user,
            access_token="stale",
            refresh_token=None,
            channel_id="UCabc",
            channel_title="My Channel",
        )
        row.token_expiry = datetime.now(tz=UTC) - timedelta(minutes=5)
        db.commit()
    finally:
        db.close()

    body = client.get("/api/v1/youtube/status", headers=auth_headers).json()
    assert body["connected"] is False
    assert body["needs_reconnect"] is True
    assert body["channel_title"] == "My Channel"
    assert "access_token" not in body


def test_status_does_not_require_oauth_config(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    body = client.get("/api/v1/youtube/status", headers=auth_headers).json()
    assert body["connected"] is False
    assert body["oauth_configured"] is False


def test_settings_saves_oauth_client_and_enables_connect(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    empty = client.get("/api/v1/youtube/oauth/app", headers=auth_headers)
    assert empty.status_code == 200
    assert empty.json()["configured"] is False
    assert empty.json()["has_secret"] is False
    assert "client_secret" not in empty.json()

    saved = client.put(
        "/api/v1/youtube/oauth/app",
        headers=auth_headers,
        json={
            "client_id": "123456789-abc.apps.googleusercontent.com",
            "client_secret": "GOCSPX-test-secret",
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["configured"] is True
    assert body["has_secret"] is True
    assert body["client_id"] == "123456789-abc.apps.googleusercontent.com"
    assert "GOCSPX" not in str(body)
    assert "client_secret" not in body

    start = client.get("/api/v1/youtube/oauth/start", headers=auth_headers)
    assert start.status_code == 200
    parsed = urlparse(start.json()["authorization_url"])
    params = parse_qs(parsed.query)
    assert params["client_id"] == ["123456789-abc.apps.googleusercontent.com"]

    again = client.get("/api/v1/youtube/oauth/app", headers=auth_headers).json()
    assert again["has_secret"] is True
    assert "GOCSPX" not in str(again)

    keep = client.put(
        "/api/v1/youtube/oauth/app",
        headers=auth_headers,
        json={"client_id": "123456789-abc.apps.googleusercontent.com"},
    )
    assert keep.status_code == 200
    assert keep.json()["has_secret"] is True
    assert "client_secret" not in keep.json()
    assert "GOCSPX" not in str(keep.json())

    start_again = client.get("/api/v1/youtube/oauth/start", headers=auth_headers)
    assert start_again.status_code == 200

    keep_empty = client.put(
        "/api/v1/youtube/oauth/app",
        headers=auth_headers,
        json={
            "client_id": "123456789-abc.apps.googleusercontent.com",
            "client_secret": "",
        },
    )
    assert keep_empty.status_code == 200
    assert keep_empty.json()["has_secret"] is True
    assert keep_empty.json()["configured"] is True

    mismatch = client.put(
        "/api/v1/youtube/oauth/app",
        headers=auth_headers,
        json={"client_id": "999999999-new.apps.googleusercontent.com"},
    )
    assert mismatch.status_code == 400


def test_env_oauth_credentials_are_used_instead_of_saved_settings(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_oauth(monkeypatch)
    saved = client.put(
        "/api/v1/youtube/oauth/app",
        headers=auth_headers,
        json={
            "client_id": "123456789-settings.apps.googleusercontent.com",
            "client_secret": "GOCSPX-settings-secret",
        },
    )
    assert saved.status_code == 200
    assert saved.json()["from_env"] is True
    assert saved.json()["client_id"] is None

    start = client.get("/api/v1/youtube/oauth/start", headers=auth_headers)
    assert start.status_code == 200
    params = parse_qs(urlparse(start.json()["authorization_url"]).query)
    assert params["client_id"] == ["test-client-id"]

    captured: dict[str, str] = {}

    def fake_token_request(self, data: dict) -> dict:
        captured.update(data)
        return {
            "access_token": "ya29.from-env",
            "refresh_token": "1//from-env",
            "expires_in": 3600,
        }

    monkeypatch.setattr(YouTubeService, "_google_token_request", fake_token_request)
    monkeypatch.setattr(
        YouTubeService,
        "_fetch_channel",
        lambda self, access_token: ("UC1", "Channel", None),
    )
    callback = client.get(
        "/api/v1/youtube/oauth/callback",
        params={"code": "live-code", "state": start.json()["state"]},
        follow_redirects=False,
    )
    assert callback.status_code == 302
    assert "connected" in callback.headers["location"]
    assert captured["client_id"] == "test-client-id"
    assert captured["client_secret"] == "test-client-secret"


def test_delete_oauth_app_clears_saved_client(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    saved = client.put(
        "/api/v1/youtube/oauth/app",
        headers=auth_headers,
        json={
            "client_id": "123456789-abc.apps.googleusercontent.com",
            "client_secret": "GOCSPX-test-secret",
        },
    )
    assert saved.status_code == 200

    gone = client.delete("/api/v1/youtube/oauth/app", headers=auth_headers)
    assert gone.status_code == 204

    empty = client.get("/api/v1/youtube/oauth/app", headers=auth_headers).json()
    assert empty["configured"] is False
    assert empty["has_secret"] is False
    assert empty["client_id"] in (None, "")
    assert "GOCSPX" not in str(empty)

    start = client.get("/api/v1/youtube/oauth/start", headers=auth_headers)
    assert start.status_code == 503

