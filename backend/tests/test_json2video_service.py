"""Unit tests for JSON2Video narrated Shorts wiring (mocked HTTP)."""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.services.video_generation_service import (
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
async def test_json2video_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIDEO_GENERATION_PROVIDER", "json2video")
    monkeypatch.setenv("JSON2VIDEO_API_KEY", "")
    get_settings.cache_clear()
    settings = get_settings()
    monkeypatch.setattr(settings, "video_generation_provider", "json2video")
    monkeypatch.setattr(settings, "json2video_api_key", None)

    with pytest.raises(VideoProviderNotConfiguredError, match="JSON2VIDEO_API_KEY"):
        await VideoGenerationService().generate(
            brief={"concept": "test", "narration": "hello world", "scenes": ["a"]},
            format="short",
        )


@pytest.mark.asyncio
async def test_json2video_poll_and_persist(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("VIDEO_GENERATION_PROVIDER", "json2video")
    monkeypatch.setenv("JSON2VIDEO_API_KEY", "test-key")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path))
    monkeypatch.setenv("STORAGE_PUBLIC_BASE_URL", "http://127.0.0.1:8000/media")
    get_settings.cache_clear()
    settings = get_settings()
    monkeypatch.setattr(settings, "video_generation_provider", "json2video")
    monkeypatch.setattr(settings, "json2video_api_key", "test-key")
    monkeypatch.setattr(settings, "replicate_api_token", None)
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "storage_local_path", str(tmp_path))
    monkeypatch.setattr(settings, "storage_public_base_url", "http://127.0.0.1:8000/media")

    import httpx

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

    polls = {"n": 0}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url: str, **kwargs):
            assert url.endswith("/movies")
            assert kwargs["headers"]["x-api-key"] == "test-key"
            body = kwargs["json"]
            assert body["quality"] == "medium"
            assert len(body["scenes"]) <= 3
            assert "elements" not in body or not body.get("elements")
            first_scene = body["scenes"][0]
            types = [el.get("type") for el in first_scene["elements"]]
            assert "text" not in types
            assert "image" not in types
            assert "video" in types
            assert "voice" in types
            video_el = next(el for el in first_scene["elements"] if el["type"] == "video")
            voice_el = next(el for el in first_scene["elements"] if el["type"] == "voice")
            assert video_el.get("model") == "seedance-v1.5-pro"
            assert video_el.get("duration") == -2
            assert first_scene.get("duration") == -1
            assert voice_el.get("duration") == -1
            prompt = video_el.get("prompt", "").lower()
            assert "cartoon" in prompt or "kids" in prompt or "storybook" in prompt
            assert "no on-screen text" in prompt
            assert "mouth" in prompt
            assert voice_el.get("text")
            return FakeResponse(200, {"success": True, "project": "abc123project01"})

        async def get(self, url: str, **kwargs):
            if "movies" in url and kwargs.get("params", {}).get("project"):
                polls["n"] += 1
                if polls["n"] == 1:
                    return FakeResponse(
                        200, {"movie": {"status": "running", "project": "abc123project01"}}
                    )
                return FakeResponse(
                    200,
                    {
                        "movie": {
                            "status": "done",
                            "url": "https://cdn.example.com/out.mp4",
                        }
                    },
                )
            return FakeResponse(200, content=b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32)

    async def _instant_sleep(_seconds):
        return None

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(
        "app.services.video_generation_service.asyncio.sleep", _instant_sleep
    )

    result = await VideoGenerationService().generate(
        brief={
            "concept": "AI Shorts tips",
            "narration": "Here are three tips to grow with AI Shorts this week.",
            "scenes": ["Hook", "Tip one", "Call to action"],
            "titles": ["Grow with AI Shorts"],
        },
        format="short",
        owner_id="user-1",
    )

    assert result.provider == "json2video"
    assert result.storage_key
    assert result.video_url.startswith("http://127.0.0.1:8000/media/")
    assert result.raw["json2video_project"] == "abc123project01"


@pytest.mark.asyncio
async def test_json2video_quota_maps_to_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VIDEO_GENERATION_PROVIDER", "json2video")
    get_settings.cache_clear()
    settings = get_settings()
    monkeypatch.setattr(settings, "video_generation_provider", "json2video")
    monkeypatch.setattr(settings, "json2video_api_key", "test-key")
    monkeypatch.setattr(settings, "replicate_api_token", None)

    import httpx

    class FakeResponse:
        status_code = 401
        text = "You exceeded the quota of movies in your plan."

        def json(self):
            return {"message": self.text}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(VideoRateLimitError, match="quota"):
        await VideoGenerationService().generate(
            brief={"narration": "Hello world", "scenes": ["Hi"]},
            format="short",
        )


@pytest.mark.asyncio
async def test_persist_falls_back_to_provider_url_on_storage_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    class BoomStorage:
        def save_bytes(self, **kwargs):
            raise TimeoutError("The write operation timed out")

    class FakeResponse:
        content = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32

        def raise_for_status(self):
            return None

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    service = VideoGenerationService()
    service._storage = BoomStorage()

    stored = await service._persist_remote_video(
        "https://cdn.example.com/out.mp4", owner_id="user-1"
    )
    assert stored["url"] == "https://cdn.example.com/out.mp4"
    assert stored["storage_key"] is None


def test_json2video_movie_is_motion_video_without_text_overlay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "json2video_voice", "en-US-AnaNeural")
    monkeypatch.setattr(settings, "json2video_video_model", "seedance-v1.5-pro")

    brief = {
        "concept": "A fox teaches counting",
        "narration": "Hi friends, let's count with Fox today.",
        "scenes": [
            "Fox waving in a sunny forest",
            "Fox and bunny counting apples",
        ],
        "visual_direction": "Pixar kids cartoon",
        "titles": ["Count with Fox"],
    }
    movie = VideoGenerationService()._json2video_movie(brief)
    element_types = [
        el.get("type") for scene in movie["scenes"] for el in scene["elements"]
    ]
    assert "text" not in element_types
    assert "image" not in element_types
    assert set(element_types) == {"video", "voice"}
    assert movie.get("quality") == "medium"
    assert len(movie["scenes"]) == 2

    crowded = VideoGenerationService()._json2video_movie(
        {
            **brief,
            "scenes": [
                "Hook",
                "Try",
                "Stumble",
                "Fix",
                "Celebrate",
                "Wave goodbye",
            ],
        }
    )
    assert len(crowded["scenes"]) == 3
    colors = {scene.get("background-color") for scene in movie["scenes"]}
    assert len(colors) == 1
    first = movie["scenes"][0]
    generated = next(el for el in first["elements"] if el["type"] == "video")
    voice = next(el for el in first["elements"] if el["type"] == "voice")
    assert generated.get("duration") == -2
    assert first.get("duration") == -1
    assert voice.get("duration") == -1
    assert voice.get("text")
    joined = " ".join(
        el["text"]
        for scene in movie["scenes"]
        for el in scene["elements"]
        if el.get("type") == "voice"
    ).lower()
    assert "fox" in joined or "count" in joined

    with_clips = VideoGenerationService()._json2video_movie(
        brief, clip_urls=["https://cdn.example.com/clip-a.mp4"]
    )
    clip_el = next(el for el in with_clips["scenes"][0]["elements"] if el["type"] == "video")
    assert clip_el["type"] == "video"
    assert clip_el["src"] == "https://cdn.example.com/clip-a.mp4"
    assert clip_el.get("muted") is True
    assert clip_el.get("resize") == "cover"
    assert clip_el.get("duration") == -2
    assert any(el.get("type") == "voice" for el in with_clips["scenes"][0]["elements"])

    prompt = VideoGenerationService()._kids_video_prompt(
        scene="Fox waving in a sunny forest",
        concept="A fox teaches counting",
        visual="Pixar kids cartoon",
        spoken_line="Hi friends, let's count with Fox today.",
    ).lower()
    assert len(prompt) <= 1024
    assert "centered" in prompt
    assert "mouth" in prompt
    assert "in sync" in prompt
    assert "no pan" in prompt
    assert "no on-screen text" in prompt
    assert "let's count with fox" in prompt

    spoken = "Hello there friends today we count apples together now."
    beats = VideoGenerationService()._split_spoken_beats(spoken, 2)
    assert len(beats) == 2
    word_re = __import__("re").compile(r"[a-z']+")
    assert word_re.findall(" ".join(beats).lower()) == word_re.findall(spoken.lower())
    assert "hello" in beats[0].lower()
    assert "now" in beats[-1].lower()

    long_prompt = VideoGenerationService()._kids_video_prompt(
        scene="A" * 800,
        concept="B" * 800,
        visual="C" * 800,
    )
    assert len(long_prompt) <= 1024
