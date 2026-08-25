"""Video provider integrations — keys stay encrypted and never return to the client."""

from fastapi.testclient import TestClient
import httpx
import pytest

from app.core.config import get_settings
from app.core.crypto import decrypt_secret
from app.models.user import User
from app.models.video_provider_credential import VideoProviderCredential
from app.services.video_generation_service import VideoGenerationService


def test_video_provider_get_requires_auth(client: TestClient) -> None:
    response = client.get("/api/v1/integrations/video")
    assert response.status_code == 401


def test_save_and_get_never_returns_api_key(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    empty = client.get("/api/v1/integrations/video", headers=auth_headers)
    assert empty.status_code == 200
    body = empty.json()
    assert body["has_key"] is False
    assert body["configured"] is False
    assert "api_key" not in body
    assert any(item["id"] == "replicate" for item in body["supported_providers"])

    saved = client.put(
        "/api/v1/integrations/video",
        headers=auth_headers,
        json={
            "provider": "replicate",
            "model_id": "minimax/video-01",
            "api_key": "r8_secret_test_token",
        },
    )
    assert saved.status_code == 200
    payload = saved.json()
    assert payload["provider"] == "replicate"
    assert payload["model_id"] == "minimax/video-01"
    assert payload["has_key"] is True
    assert payload["configured"] is True
    assert payload["source"] == "settings"
    assert "api_key" not in payload
    assert "r8_secret" not in str(payload)

    db = client.session_local()
    try:
        row = db.query(VideoProviderCredential).one()
        user = db.query(User).one()
        assert row.user_id == user.id
        assert "r8_secret" not in row.api_key_encrypted
        assert decrypt_secret(row.api_key_encrypted, get_settings().jwt_secret) == (
            "r8_secret_test_token"
        )
    finally:
        db.close()

    keep = client.put(
        "/api/v1/integrations/video",
        headers=auth_headers,
        json={"provider": "replicate", "model_id": "minimax/video-01"},
    )
    assert keep.status_code == 200
    assert keep.json()["has_key"] is True
    assert "r8_secret" not in str(keep.json())


def test_save_rejects_unsupported_provider(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.put(
        "/api/v1/integrations/video",
        headers=auth_headers,
        json={"provider": "openai", "api_key": "sk-test"},
    )
    assert response.status_code == 400


def test_video_credentials_are_scoped_to_owner(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    saved = client.put(
        "/api/v1/integrations/video",
        headers=auth_headers,
        json={"provider": "replicate", "api_key": "r8_owner_only_key"},
    )
    assert saved.status_code == 200
    other = client.post(
        "/api/v1/auth/register",
        json={"email": "other@example.com", "password": "securepass1"},
    )
    assert other.status_code == 201
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    body = client.get("/api/v1/integrations/video", headers=other_headers).json()
    assert body["has_key"] is False
    assert body["configured"] is False
    assert "r8_owner" not in str(body)
    assert "api_key" not in body


def test_delete_clears_saved_key(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.put(
        "/api/v1/integrations/video",
        headers=auth_headers,
        json={"provider": "replicate", "api_key": "r8_to_delete"},
    )
    gone = client.delete("/api/v1/integrations/video", headers=auth_headers)
    assert gone.status_code == 204
    body = client.get("/api/v1/integrations/video", headers=auth_headers).json()
    assert body["has_key"] is False
    assert "r8_to_delete" not in str(body)


@pytest.mark.asyncio
async def test_test_connection_uses_saved_key(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    client.put(
        "/api/v1/integrations/video",
        headers=auth_headers,
        json={"provider": "replicate", "api_key": "r8_live_token"},
    )

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"username": "creator-os"}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, headers=None):
            assert url.endswith("/account")
            assert headers["Authorization"] == "Bearer r8_live_token"
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    response = client.post(
        "/api/v1/integrations/video/test",
        headers=auth_headers,
        json={"provider": "replicate"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["account"] == "creator-os"
    assert "r8_live" not in str(data)


def test_test_connection_rejects_bad_key(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeResponse:
        status_code = 401

        def json(self):
            return {"detail": "Unauthenticated"}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, headers=None):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    response = client.post(
        "/api/v1/integrations/video/test",
        headers=auth_headers,
        json={"provider": "replicate", "api_key": "r8_bad"},
    )
    assert response.status_code == 400
    assert "r8_bad" not in str(response.json())


@pytest.mark.asyncio
async def test_generate_uses_settings_replicate_without_env_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("VIDEO_GENERATION_PROVIDER", "json2video")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path))
    monkeypatch.setenv("STORAGE_PUBLIC_BASE_URL", "http://127.0.0.1:8000/media")
    get_settings.cache_clear()
    settings = get_settings()
    monkeypatch.setattr(settings, "video_generation_provider", "json2video")
    monkeypatch.setattr(settings, "json2video_api_key", "j2v-env")
    monkeypatch.setattr(settings, "replicate_api_token", None)
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "storage_local_path", str(tmp_path))
    monkeypatch.setattr(settings, "storage_public_base_url", "http://127.0.0.1:8000/media")

    captured = {}

    class FakeResponse:
        def __init__(self, status_code, payload=None, content=b""):
            self.status_code = status_code
            self._payload = payload or {}
            self.content = content
            self.text = str(payload)

        def json(self):
            return self._payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            captured["url"] = url
            captured["auth"] = kwargs["headers"]["Authorization"]
            captured["json"] = kwargs["json"]
            return FakeResponse(201, {"id": "pred_1", "status": "succeeded", "output": "https://cdn.example.com/out.mp4"})

        async def get(self, url, **kwargs):
            if "cdn.example.com" in url:
                return FakeResponse(200, content=b"mp4-bytes")
            return FakeResponse(200, {"id": "pred_1", "status": "succeeded", "output": "https://cdn.example.com/out.mp4"})

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    result = await VideoGenerationService().generate(
        brief={"concept": "fox", "scenes": ["a"], "visual_direction": "cartoon"},
        video_provider={
            "provider": "replicate",
            "api_key": "r8_from_settings",
            "model_id": "minimax/video-01",
        },
    )
    assert result.provider == "replicate"
    assert captured["auth"] == "Bearer r8_from_settings"
    assert captured["url"].endswith("/models/minimax/video-01/predictions")
    assert "version" not in captured["json"]
    assert result.video_url
