"""Unit tests for Supabase Storage backend (mocked HTTP)."""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.services.storage_service import StorageError, StorageService


@pytest.fixture(autouse=True)
def _clear_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_supabase_rejects_publishable_as_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_publishable_abc")
    get_settings.cache_clear()
    settings = get_settings()
    monkeypatch.setattr(settings, "storage_backend", "supabase")
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_secret_key", "sb_publishable_abc")
    monkeypatch.setattr(settings, "supabase_key", None)

    with pytest.raises(StorageError, match="secret/service_role"):
        StorageService().save_bytes(
            data=b"abc", owner_id="user-1", suffix=".mp4"
        )


def test_supabase_upload_and_sign(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "supabase")
    get_settings.cache_clear()
    settings = get_settings()
    monkeypatch.setattr(settings, "storage_backend", "supabase")
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_secret_key", "sb_secret_test")
    monkeypatch.setattr(settings, "supabase_key", None)

    calls: list[tuple[str, str]] = []

    class FakeResponse:
        def __init__(self, status_code: int, payload=None, text: str = ""):
            self.status_code = status_code
            self._payload = payload
            self.text = text

        def json(self):
            return self._payload

    def fake_get(url, headers=None, timeout=None):
        calls.append(("GET", url))
        if url.endswith("/storage/v1/bucket"):
            return FakeResponse(200, [])
        raise AssertionError(url)

    def fake_post(url, headers=None, json=None, content=None, timeout=None):
        calls.append(("POST", url))
        if url.endswith("/storage/v1/bucket"):
            assert json["id"] == "videos"
            assert json["public"] is False
            return FakeResponse(201, {"name": "videos"})
        if "/storage/v1/object/videos/" in url and content is not None:
            assert content == b"fake-mp4"
            assert "user-99/" in url
            return FakeResponse(200, {"Key": "videos/user-99/x.mp4"})
        if "/storage/v1/object/sign/videos/" in url:
            return FakeResponse(200, {"signedURL": "/object/sign/videos/user-99/x.mp4?token=abc"})
        raise AssertionError(url)

    monkeypatch.setattr("app.services.storage_service.httpx.get", fake_get)
    monkeypatch.setattr("app.services.storage_service.httpx.post", fake_post)

    result = StorageService().save_bytes(
        data=b"fake-mp4", owner_id="user-99", suffix=".mp4"
    )
    assert result["storage_key"].startswith("videos/user-99/")
    assert result["url"].startswith("https://example.supabase.co/storage/v1/")
    assert any("sign" in u for m, u in calls if m == "POST")


def test_assert_owner_path() -> None:
    StorageService().assert_owner_path("videos/user-1/a.mp4", "user-1")
    with pytest.raises(StorageError):
        StorageService().assert_owner_path("videos/user-2/a.mp4", "user-1")
