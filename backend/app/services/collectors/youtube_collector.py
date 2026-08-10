from datetime import UTC, datetime, timedelta

import httpx

from app.core.config import get_settings
from app.services.collectors.base import (
    CollectedItem,
    CollectorError,
    CollectorNotConfiguredError,
    TrendCollector,
)


class YouTubeCollector(TrendCollector):
    """Fetches real videos via the YouTube Data API v3.

    Requires YOUTUBE_API_KEY. If it isn't configured, raises
    CollectorNotConfiguredError rather than fabricating results — the caller
    (TrendService) turns this into a visible warning, never silent fake data.
    """

    source_name = "youtube"
    SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
    VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"

    def __init__(self, timeout: float = 10.0) -> None:
        self._timeout = timeout

    async def collect(self, query: str, limit: int = 10) -> list[CollectedItem]:
        settings = get_settings()
        api_key = settings.youtube_api_key
        if not api_key:
            raise CollectorNotConfiguredError(
                "YOUTUBE_API_KEY is not set; YouTube trend collection is disabled."
            )

        published_after = (datetime.now(tz=UTC) - timedelta(days=14)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        search_params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "order": "viewCount",
            "publishedAfter": published_after,
            "maxResults": min(limit, 25),
            "key": api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                search_response = await client.get(self.SEARCH_URL, params=search_params)
                search_response.raise_for_status()
                search_payload = search_response.json()

                video_ids = [
                    item["id"]["videoId"]
                    for item in search_payload.get("items", [])
                    if item.get("id", {}).get("videoId")
                ]
                if not video_ids:
                    return []

                stats_response = await client.get(
                    self.VIDEOS_URL,
                    params={
                        "part": "snippet,statistics",
                        "id": ",".join(video_ids),
                        "key": api_key,
                    },
                )
                stats_response.raise_for_status()
                stats_payload = stats_response.json()
        except httpx.HTTPStatusError as exc:
            raise CollectorError(
                f"YouTube API returned HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise CollectorError(f"YouTube API request failed: {exc}") from exc
        except ValueError as exc:
            raise CollectorError("YouTube API returned an unparseable response") from exc

        items: list[CollectedItem] = []
        for video in stats_payload.get("items", []):
            snippet = video.get("snippet", {})
            statistics = video.get("statistics", {})
            video_id = video.get("id")
            title = snippet.get("title")
            if not video_id or not title:
                continue

            published_at_raw = snippet.get("publishedAt")
            published_at = (
                datetime.fromisoformat(published_at_raw.replace("Z", "+00:00"))
                if published_at_raw
                else None
            )

            items.append(
                CollectedItem(
                    title=title,
                    source=self.source_name,
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    published_at=published_at,
                    metrics={
                        "views": int(statistics.get("viewCount", 0) or 0),
                        "likes": int(statistics.get("likeCount", 0) or 0),
                        "comments": int(statistics.get("commentCount", 0) or 0),
                        "channel": snippet.get("channelTitle"),
                    },
                )
            )
        return items
