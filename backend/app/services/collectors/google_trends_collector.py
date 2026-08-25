import re
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET

import httpx

from app.core.config import get_settings
from app.services.collectors.base import CollectedItem, CollectorError, TrendCollector

_NS = {"ht": "https://trends.google.com/trending/rss"}
_TRAFFIC_RE = re.compile(r"([\d.]+)\s*([KM]?)", re.IGNORECASE)
_TRAFFIC_MULTIPLIERS = {"K": 1_000, "M": 1_000_000}
_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _is_relevant(query: str, haystack: str) -> bool:
    """Whole-word AND match: every keyword in the query must appear in the
    haystack (item title + related news headlines).

    Substring matching on common short words (e.g. "home", "tips") produced
    false positives against Google's unrelated daily trending searches, so
    this requires every keyword to be genuinely present as its own word —
    stricter, but honest about the fact this feed isn't query-scoped.
    """
    keywords = {word for word in _tokenize(query) if len(word) > 2}
    if not keywords:
        # All tokens were too short to match honestly (e.g. niche "AI" / "VR").
        # Returning True would ingest the entire unrelated daily feed — refuse
        # rather than fabricate relevance the source can't provide.
        return False
    haystack_words = _tokenize(haystack)
    return keywords.issubset(haystack_words)


def _parse_approx_traffic(raw: str | None) -> int:
    """Parses Google's "200+" / "5K+" / "1M+" traffic strings into a rough int.

    Returns 0 if unparseable rather than guessing — never fabricate a number
    the source didn't actually provide (Constitution §14).
    """
    if not raw:
        return 0
    match = _TRAFFIC_RE.search(raw.strip())
    if not match:
        return 0
    number = float(match.group(1))
    multiplier = _TRAFFIC_MULTIPLIERS.get(match.group(2).upper(), 1)
    return int(number * multiplier)


class GoogleTrendsCollector(TrendCollector):
    """Fetches real daily trending searches from Google Trends' public RSS feed.

    Google Trends has no official public API for keyword-scoped queries
    (verified — Constitution §16 forbids assuming/inventing one). The only
    genuinely public, unauthenticated endpoint is the daily trending
    searches RSS feed (`trends.google.com/trending/rss`), which lists that
    day's top trending searches for a region — it is NOT scoped to a search
    term. To stay honest rather than inventing a targeted API, this
    collector fetches the daily list and keeps only items where every
    keyword in the requested query appears as a whole word in the item's
    title or its related news headlines (see `_is_relevant`).

    For narrow niches this will often legitimately return zero results —
    that's expected, not a bug (never fabricate relevance the source
    doesn't provide).
    """

    source_name = "google_trends"
    RSS_URL = "https://trends.google.com/trending/rss"

    def __init__(self, timeout: float = 10.0) -> None:
        self._timeout = timeout

    async def collect(
        self,
        query: str,
        limit: int = 10,
        *,
        exclude_urls: set[str] | None = None,
    ) -> list[CollectedItem]:
        settings = get_settings()
        excluded = exclude_urls or set()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    self.RSS_URL, params={"geo": settings.google_trends_geo}
                )
                response.raise_for_status()
                xml_text = response.text
        except httpx.HTTPStatusError as exc:
            raise CollectorError(
                f"Google Trends returned HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise CollectorError(f"Google Trends request failed: {exc}") from exc

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise CollectorError("Google Trends returned unparseable XML") from exc

        items: list[CollectedItem] = []
        for item_el in root.findall(".//item"):
            title = (item_el.findtext("title") or "").strip()
            if not title:
                continue

            news_titles = [
                el.findtext("ht:news_item_title", default="", namespaces=_NS) or ""
                for el in item_el.findall("ht:news_item", _NS)
            ]
            haystack = " ".join([title, *news_titles])
            if not _is_relevant(query, haystack):
                continue

            traffic_raw = item_el.findtext("ht:approx_traffic", default="", namespaces=_NS)
            published_at = None
            pub_date_raw = item_el.findtext("pubDate")
            if pub_date_raw:
                try:
                    published_at = parsedate_to_datetime(pub_date_raw)
                except (TypeError, ValueError):
                    published_at = None

            url = f"https://trends.google.com/trends/explore?q={quote_plus(title)}"
            if url in excluded:
                continue

            items.append(
                CollectedItem(
                    title=title,
                    source=self.source_name,
                    url=url,
                    published_at=published_at,
                    metrics={
                        "approx_traffic": traffic_raw or None,
                        "approx_traffic_numeric": _parse_approx_traffic(traffic_raw),
                        "related_articles": len(news_titles),
                    },
                )
            )
            if len(items) >= limit:
                break

        return items
