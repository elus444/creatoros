from datetime import UTC, datetime, timedelta
import logging
import re

import httpx

from app.core.config import get_settings
from app.services.collectors.base import (
    CollectedItem,
    CollectorError,
    CollectorNotConfiguredError,
    TrendCollector,
)

logger = logging.getLogger("creatoros.trends.youtube")

# YouTube Shorts are vertical clips up to 3 minutes. API `videoDuration=short`
# is under 4 minutes, so duration is the real Shorts gate — not an HTML probe.
# YouTube often redirects /shorts/{id} → /watch?v= for non-browser clients,
# so a watch Location is not evidence the video is long-form.
_SHORTS_MAX_SECONDS = 180
_SEARCH_WINDOW_DAYS = 21
_SEARCH_WINDOW_FALLBACK_DAYS = 45
_DURATION_RE = re.compile(
    r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$"
)


def _safe_nonnegative_int(value: object) -> int:
    """Normalize optional provider counters without trusting malformed data."""
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _video_id_from_url(url: str) -> str | None:
    if "/shorts/" in url:
        return url.split("/shorts/", 1)[1].split("?", 1)[0].split("&", 1)[0] or None
    marker = "watch?v="
    if marker not in url:
        return None
    return url.split(marker, 1)[1].split("&", 1)[0] or None


def _duration_seconds(value: object) -> int | None:
    if not isinstance(value, str) or not value.startswith("PT"):
        return None
    match = _DURATION_RE.fullmatch(value)
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = float(match.group(3) or 0)
    return int(hours * 3600 + minutes * 60 + seconds)


def _is_not_for_kids(status: dict) -> bool:
    """True when YouTube's COPPA flag is explicitly false.

    This is the default for most real Shorts, not a signal of adult content.
    Age-restricted videos are handled separately.
    """
    if status.get("madeForKids") is False:
        return True
    if status.get("selfDeclaredMadeForKids") is False:
        return True
    return False


def _is_age_restricted(details: dict) -> bool:
    rating = (details.get("contentRating") or {}).get("ytRating")
    return rating == "ytAgeRestricted"


class YouTubeCollector(TrendCollector):
    """Fetches real videos via the YouTube Data API v3.

    Requires YOUTUBE_API_KEY. If it isn't configured, raises
    CollectorNotConfiguredError rather than fabricating results — the caller
    (TrendService) turns this into a visible warning, never silent fake data.

    Shorts: search queries include "shorts", `videoDuration=short`, and
    duration ≤ 3 minutes. Age-restricted videos are dropped. `madeForKids`
    is recorded but not used as a hard reject (COPPA default is false).
    """

    source_name = "youtube"
    SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
    VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout
        self.last_stats: dict[str, int] = {}

    @staticmethod
    async def _confirm_is_short(client: httpx.AsyncClient, video_id: str) -> bool | None:
        """Best-effort HTML probe. Watch redirects are inconclusive, not a no.

        None means the probe could not confirm either way. Callers must not
        treat None or a watch redirect as "not a Short".
        """
        try:
            response = await client.get(
                f"https://www.youtube.com/shorts/{video_id}",
                follow_redirects=False,
                headers={"User-Agent": "Mozilla/5.0"},
            )
        except httpx.HTTPError:
            return None
        location = (response.headers.get("location") or "").lower()
        if "/shorts/" in location:
            return True
        if "/watch" in location:
            # YouTube routinely sends Shorts to /watch for non-browser clients.
            return None
        if response.status_code < 400:
            return True
        return None

    def _query_variants(self, query: str) -> list[str]:
        """Shorts search strings, English-first.

        Generic kids/AI queries are flooded by Hindi-audio farms that still
        use English hashtags. Put `english` in the query before the bare niche.
        Never search the bare niche without shorts — that pulls long-form.
        """
        base = query.strip()
        if not base:
            return ["english #shorts"]

        lowered = base.lower()
        has_short = "short" in lowered
        has_english = "english" in lowered
        variants: list[str] = []

        def add(text: str) -> None:
            cleaned = " ".join(text.split())
            if cleaned and cleaned.lower() not in {item.lower() for item in variants}:
                variants.append(cleaned)

        if has_short:
            if not has_english:
                add(f"{base} english")
            add(base)
        else:
            if not has_english:
                add(f"{base} english #shorts")
                add(f"{base} english shorts")
            add(f"{base} #shorts")
            add(f"{base} shorts")
        return variants

    async def _search_ids(
        self,
        client: httpx.AsyncClient,
        *,
        variants: list[str],
        api_key: str,
        published_after: str,
        per_search: int,
        excluded_ids: set[str],
        pool_target: int,
        orders: tuple[str, ...] = ("relevance", "viewCount"),
    ) -> list[str]:
        video_ids: list[str] = []
        seen_ids: set[str] = set()
        settings = get_settings()
        for variant in variants:
            for order in orders:
                search_response = await client.get(
                    self.SEARCH_URL,
                    params={
                        "part": "snippet",
                        "q": variant,
                        "type": "video",
                        "videoDuration": "short",
                        "safeSearch": "strict",
                        "order": order,
                        "publishedAfter": published_after,
                        "maxResults": per_search,
                        "relevanceLanguage": "en",
                        "regionCode": settings.google_trends_geo or "US",
                        "key": api_key,
                    },
                )
                search_response.raise_for_status()
                search_payload = search_response.json()
                for item in search_payload.get("items", []):
                    video_id = item.get("id", {}).get("videoId")
                    if (
                        not video_id
                        or video_id in seen_ids
                        or video_id in excluded_ids
                    ):
                        continue
                    seen_ids.add(video_id)
                    video_ids.append(video_id)
                if len(video_ids) >= pool_target:
                    return video_ids
        return video_ids

    async def collect(
        self,
        query: str,
        limit: int = 10,
        *,
        exclude_urls: set[str] | None = None,
    ) -> list[CollectedItem]:
        settings = get_settings()
        api_key = settings.youtube_api_key
        if not api_key:
            raise CollectorNotConfiguredError(
                "YOUTUBE_API_KEY is not set; YouTube trend collection is disabled."
            )

        excluded = exclude_urls or set()
        excluded_ids = {
            video_id
            for video_id in (_video_id_from_url(url) for url in excluded)
            if video_id
        }

        per_search = min(max(limit, 15), 25)
        # videos.list accepts 50 ids. Fetch a wide English-biased pool so the
        # language gate still has enough spoken-English Shorts left.
        pool_target = min(50, max(limit * 5, 40))
        variants = self._query_variants(query)
        stats = {
            "youtube_results": 0,
            "details_fetched": 0,
            "shorts_filter": 0,
            "age_restricted_dropped": 0,
            "duration_unparsed": 0,
            "long_form_dropped": 0,
        }
        self.last_stats = stats

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                video_ids: list[str] = []
                used_days = _SEARCH_WINDOW_DAYS
                for days in (_SEARCH_WINDOW_DAYS, _SEARCH_WINDOW_FALLBACK_DAYS):
                    published_after = (
                        datetime.now(tz=UTC) - timedelta(days=days)
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")
                    video_ids = await self._search_ids(
                        client,
                        variants=variants,
                        api_key=api_key,
                        published_after=published_after,
                        per_search=per_search,
                        excluded_ids=excluded_ids,
                        pool_target=pool_target,
                    )
                    used_days = days
                    if video_ids:
                        break

                stats["youtube_results"] = len(video_ids)
                stats["search_window_days"] = used_days
                logger.info(
                    "YouTube results: %s (query=%r window=%sd variants=%s)",
                    len(video_ids),
                    query,
                    used_days,
                    variants,
                )
                if not video_ids:
                    return []

                stats_response = await client.get(
                    self.VIDEOS_URL,
                    params={
                        "part": "snippet,statistics,contentDetails,status",
                        "id": ",".join(video_ids[:50]),
                        "key": api_key,
                    },
                )
                stats_response.raise_for_status()
                stats_payload = stats_response.json()

                by_id = {
                    video.get("id"): video for video in stats_payload.get("items", [])
                }
                stats["details_fetched"] = len(by_id)
                logger.info("Video details fetched: %s", len(by_id))

                items: list[CollectedItem] = []
                for video_id in video_ids:
                    video = by_id.get(video_id)
                    if not video:
                        continue
                    snippet = video.get("snippet", {}) or {}
                    statistics = video.get("statistics", {}) or {}
                    details = video.get("contentDetails", {}) or {}
                    status = video.get("status", {}) or {}
                    title = snippet.get("title")
                    if not title:
                        continue
                    if _is_age_restricted(details):
                        stats["age_restricted_dropped"] += 1
                        continue
                    duration_seconds = _duration_seconds(details.get("duration"))
                    if duration_seconds is None or duration_seconds <= 0:
                        stats["duration_unparsed"] += 1
                        continue
                    if duration_seconds > _SHORTS_MAX_SECONDS:
                        stats["long_form_dropped"] += 1
                        continue

                    published_at_raw = snippet.get("publishedAt")
                    try:
                        published_at = (
                            datetime.fromisoformat(
                                published_at_raw.replace("Z", "+00:00")
                            )
                            if isinstance(published_at_raw, str)
                            else None
                        )
                    except ValueError:
                        published_at = None

                    url = f"https://www.youtube.com/shorts/{video_id}"
                    if url in excluded:
                        continue

                    items.append(
                        CollectedItem(
                            title=title,
                            source=self.source_name,
                            url=url,
                            published_at=published_at,
                            description=_optional_str(snippet.get("description")),
                            default_language=_optional_str(snippet.get("defaultLanguage")),
                            default_audio_language=_optional_str(
                                snippet.get("defaultAudioLanguage")
                            ),
                            metrics={
                                "views": _safe_nonnegative_int(
                                    statistics.get("viewCount")
                                ),
                                "likes": _safe_nonnegative_int(
                                    statistics.get("likeCount")
                                ),
                                "comments": _safe_nonnegative_int(
                                    statistics.get("commentCount")
                                ),
                                "channel": snippet.get("channelTitle"),
                                "duration_seconds": duration_seconds,
                                "made_for_kids": status.get("madeForKids"),
                                "default_language": _optional_str(
                                    snippet.get("defaultLanguage")
                                ),
                                "default_audio_language": _optional_str(
                                    snippet.get("defaultAudioLanguage")
                                ),
                            },
                        )
                    )
                    if len(items) >= pool_target:
                        break

                stats["shorts_filter"] = len(items)
                logger.info(
                    "Shorts filter: %s remaining "
                    "(age_restricted=%s unparsed_duration=%s long_form=%s)",
                    len(items),
                    stats["age_restricted_dropped"],
                    stats["duration_unparsed"],
                    stats["long_form_dropped"],
                )
                return items
        except httpx.HTTPStatusError as exc:
            raise CollectorError(
                f"YouTube API returned HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise CollectorError(f"YouTube API request failed: {exc}") from exc
        except ValueError as exc:
            raise CollectorError("YouTube API returned an unparseable response") from exc
