"""Unit tests for Replicate video generation wiring (no live network by default)."""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.services.video_generation_service import (
    REPLICATE_VERSION,
    VideoGenerationService,
    VideoProviderNotConfiguredError,
    VideoRateLimitError,
)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_replicate_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIDEO_GENERATION_PROVIDER", "replicate")
    monkeypatch.setenv("REPLICATE_API_TOKEN", "")
    get_settings.cache_clear()
    settings = get_settings()
    monkeypatch.setattr(settings, "video_generation_provider", "replicate")
    monkeypatch.setattr(settings, "replicate_api_token", None)

    with pytest.raises(VideoProviderNotConfiguredError, match="REPLICATE_API_TOKEN"):
        await VideoGenerationService().generate(
            brief={"concept": "test", "scenes": ["a"], "visual_direction": "v"},
            format="short",
        )


@pytest.mark.asyncio
async def test_replicate_poll_and_persist(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("VIDEO_GENERATION_PROVIDER", "replicate")
    monkeypatch.setenv("REPLICATE_API_TOKEN", "r8_test_token")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path))
    monkeypatch.setenv("STORAGE_PUBLIC_BASE_URL", "http://127.0.0.1:8000/media")
    get_settings.cache_clear()
    settings = get_settings()
    monkeypatch.setattr(settings, "video_generation_provider", "replicate")
    monkeypatch.setattr(settings, "replicate_api_token", "r8_test_token")
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "storage_local_path", str(tmp_path))
    monkeypatch.setattr(settings, "storage_public_base_url", "http://127.0.0.1:8000/media")

    import httpx

    calls = {"n": 0}

    class FakeResponse:
        def __init__(self, status_code: int, payload: dict | None = None, content: bytes = b""):
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

        async def post(self, url, headers=None, json=None):
            assert url.endswith("/predictions")
            assert json["version"] == REPLICATE_VERSION
            assert set(json["input"].keys()) == {
                "prompt",
                "prompt_optimizer",
                "first_frame_image",
            }
            assert json["input"]["prompt_optimizer"] is True
            assert json["input"]["first_frame_image"].startswith("data:image/png;base64,")
            assert "9:16" in json["input"]["prompt"] or "Vertical" in json["input"]["prompt"]
            return FakeResponse(
                201,
                {"id": "pred_123", "status": "starting"},
            )

        async def get(self, url, headers=None):
            calls["n"] += 1
            if "predictions/pred_123" in url:
                if calls["n"] == 1:
                    return FakeResponse(200, {"id": "pred_123", "status": "processing"})
                return FakeResponse(
                    200,
                    {
                        "id": "pred_123",
                        "status": "succeeded",
                        "output": "https://cdn.example.com/replicate-out.mp4",
                    },
                )
            assert url == "https://cdn.example.com/replicate-out.mp4"
            return FakeResponse(200, content=b"fake-mp4-bytes")

    monkeypatch.setattr(
        "app.services.video_generation_service.httpx.AsyncClient", FakeAsyncClient
    )

    async def _no_sleep(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "app.services.video_generation_service.asyncio.sleep", _no_sleep
    )

    result = await VideoGenerationService().generate(
        brief={
            "concept": "A creator opens a laptop",
            "scenes": ["hook", "demo"],
            "visual_direction": "Bright vertical framing",
            "narration": "Watch this tip",
            "duration_seconds": 5,
        },
        format="short",
    )

    assert result.provider == "replicate"
    assert result.storage_key
    assert result.video_url.startswith("http://127.0.0.1:8000/media/")
    assert (tmp_path / result.storage_key).read_bytes() == b"fake-mp4-bytes"


@pytest.mark.asyncio
async def test_replicate_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIDEO_GENERATION_PROVIDER", "replicate")
    get_settings.cache_clear()
    settings = get_settings()
    monkeypatch.setattr(settings, "video_generation_provider", "replicate")
    monkeypatch.setattr(settings, "replicate_api_token", "r8_test_token")

    class FakeResponse:
        status_code = 429
        text = "rate limit"

        def json(self):
            return {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(
        "app.services.video_generation_service.httpx.AsyncClient", FakeAsyncClient
    )

    with pytest.raises(VideoRateLimitError, match="rate limit"):
        await VideoGenerationService().generate(
            brief={"concept": "x", "scenes": ["a"], "visual_direction": "v"},
            format="short",
        )
