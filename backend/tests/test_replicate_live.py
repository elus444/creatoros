"""Live Replicate smoke (costs credits).

Excluded from the default test run (see pytest.ini `addopts = -m "not live"`)
so this can never fire unattended in CI just because a real
REPLICATE_API_TOKEN happens to be configured in the environment.

Run deliberately, with real credentials, when you want to spend credits:
  .venv\\Scripts\\python.exe -m pytest tests/test_replicate_live.py -m live -q -s --tb=short
"""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.services.video_generation_service import VideoGenerationService

pytestmark = pytest.mark.live


@pytest.mark.asyncio
async def test_live_replicate_generates_short_video(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    get_settings.cache_clear()
    settings = get_settings()
    if not settings.replicate_api_token:
        pytest.skip("REPLICATE_API_TOKEN not configured")

    monkeypatch.setenv("VIDEO_GENERATION_PROVIDER", "replicate")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path))
    monkeypatch.setenv("STORAGE_PUBLIC_BASE_URL", "http://127.0.0.1:8000/media")
    get_settings.cache_clear()
    live = get_settings()
    monkeypatch.setattr(live, "video_generation_provider", "replicate")
    monkeypatch.setattr(live, "replicate_api_token", settings.replicate_api_token)
    monkeypatch.setattr(live, "storage_backend", "local")
    monkeypatch.setattr(live, "storage_local_path", str(tmp_path))
    monkeypatch.setattr(live, "storage_public_base_url", "http://127.0.0.1:8000/media")

    result = await VideoGenerationService().generate(
        brief={
            "concept": "Close-up of hands typing on a laptop in soft daylight, vertical framing",
            "scenes": ["hands on keyboard", "screen glow"],
            "visual_direction": "9:16 YouTube Shorts, natural light, gentle camera push-in",
            "narration": "One tip to ship content faster.",
            "duration_seconds": 2,
        },
        format="short",
    )

    assert result.provider == "replicate"
    assert result.video_url
    assert result.storage_key
    stored = tmp_path / result.storage_key
    assert stored.exists()
    assert stored.stat().st_size > 1000
    print(
        f"LIVE_REPLICATE_OK url={result.video_url} "
        f"bytes={stored.stat().st_size} key={result.storage_key}"
    )
