"""YouTube collector: Shorts-only, kids-safe, resilient to malformed metadata."""

import httpx
import pytest

from app.core.config import get_settings
from app.services.collectors.youtube_collector import (
    YouTubeCollector,
    _duration_seconds,
    _is_not_for_kids,
)


class _Response:
    def __init__(
        self,
        body: dict,
        status_code: int = 200,
        headers: dict | None = None,
    ) -> None:
        self._body = body
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._body


def _video(
    video_id: str,
    *,
    duration: str = "PT45S",
    made_for_kids: bool | None = True,
    title: str = "Kids counting Short",
    extra_details: dict | None = None,
    extra_status: dict | None = None,
) -> dict:
    details = {"duration": duration, **(extra_details or {})}
    status = extra_status or {}
    if made_for_kids is not None:
        status["madeForKids"] = made_for_kids
    return {
        "id": video_id,
        "snippet": {
            "title": title,
            "publishedAt": "not-a-date",
            "channelTitle": "Creator",
            "description": "A short kids video",
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "statistics": {
            "viewCount": "not-a-number",
            "likeCount": "-4",
            "commentCount": None,
        },
        "contentDetails": details,
        "status": status,
    }


class _Client:
    last_search_params: dict | None = None
    last_videos_params: dict | None = None
    search_queries: list[str] = []
    videos: list[dict] = []
    watch_ids: set[str] = set()
    fail_ids: set[str] = set()

    def __init__(self, *args, **kwargs) -> None:
        self.search_calls = 0

    async def __aenter__(self) -> "_Client":
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def get(self, url: str, params: dict | None = None, **kwargs) -> _Response:
        if "youtube.com/shorts/" in url:
            video_id = url.rstrip("/").rsplit("/", 1)[-1]
            if video_id in type(self).watch_ids:
                return _Response(
                    {},
                    status_code=303,
                    headers={"location": f"https://www.youtube.com/watch?v={video_id}"},
                )
            if video_id in type(self).fail_ids:
                return _Response({}, status_code=404)
            return _Response({}, status_code=200)
        if url == YouTubeCollector.SEARCH_URL:
            self.search_calls += 1
            type(self).last_search_params = params or {}
            type(self).search_queries.append((params or {}).get("q", ""))
            return _Response(
                {
                    "items": [
                        {"id": {"videoId": video["id"]}} for video in type(self).videos
                    ]
                }
            )
        type(self).last_videos_params = params or {}
        return _Response({"items": list(type(self).videos)})


@pytest.fixture
def youtube_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(get_settings(), "youtube_api_key", "test-key")
    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    _Client.last_search_params = None
    _Client.last_videos_params = None
    _Client.search_queries = []
    _Client.videos = [_video("abc123")]
    _Client.watch_ids = set()
    _Client.fail_ids = set()
    return _Client


@pytest.mark.asyncio
async def test_collector_searches_shorts_only_and_keeps_kids_safe_clips(
    youtube_client,
) -> None:
    items = await YouTubeCollector().collect("creator tools")

    assert youtube_client.search_queries
    assert all("short" in q.lower() for q in youtube_client.search_queries)
    assert "creator tools" not in youtube_client.search_queries
    assert any("english" in q.lower() for q in youtube_client.search_queries)
    assert youtube_client.last_search_params["videoDuration"] == "short"
    assert youtube_client.last_search_params["order"] in {"relevance", "viewCount", "date"}
    assert youtube_client.last_search_params["safeSearch"] == "strict"
    assert "contentDetails" in youtube_client.last_videos_params["part"]
    assert "status" in youtube_client.last_videos_params["part"]
    assert len(items) == 1
    assert items[0].url == "https://www.youtube.com/shorts/abc123"
    assert items[0].metrics["duration_seconds"] == 45
    assert items[0].published_at is None
    assert items[0].metrics["views"] == 0


@pytest.mark.asyncio
async def test_collector_keeps_english_shorts_and_drops_long_form_and_age_restricted(
    youtube_client,
) -> None:
    _Client.videos = [
        _video("long1", duration="PT8M12S", title="Long tutorial"),
        _video(
            "adult1",
            duration="PT40S",
            made_for_kids=False,
            title="Normal Short not marked for kids",
        ),
        _video(
            "age1",
            duration="PT30S",
            title="Age restricted clip",
            extra_details={"contentRating": {"ytRating": "ytAgeRestricted"}},
        ),
        _video("watch1", duration="PT90S", title="Short that redirects to watch"),
        _video("ok1", duration="PT30S", made_for_kids=True, title="Kids Short"),
    ]
    _Client.watch_ids = {"watch1"}
    items = await YouTubeCollector().collect("counting")
    assert [item.url for item in items] == [
        "https://www.youtube.com/shorts/adult1",
        "https://www.youtube.com/shorts/watch1",
        "https://www.youtube.com/shorts/ok1",
    ]
    assert items[0].metrics["made_for_kids"] is False


def test_duration_and_kids_helpers() -> None:
    assert _duration_seconds("PT45S") == 45
    assert _duration_seconds("PT1M30S") == 90
    assert _duration_seconds("PT3M") == 180
    assert _duration_seconds("PT8M") == 480
    assert _is_not_for_kids({"madeForKids": False}) is True
    assert _is_not_for_kids({"madeForKids": True}) is False
    assert _is_not_for_kids({}) is False
