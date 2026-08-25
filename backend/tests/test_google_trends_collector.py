"""Unit tests for GoogleTrendsCollector's RSS parsing and keyword filtering.

Network calls are faked at the httpx.AsyncClient level with a canned RSS
payload shaped like the real feed (verified live against
trends.google.com/trending/rss during implementation) — no real network
access happens in this suite.
"""

import httpx
import pytest

from app.services.collectors.base import CollectorError
from app.services.collectors.google_trends_collector import (
    GoogleTrendsCollector,
    _is_relevant,
    _parse_approx_traffic,
)

# The global autouse fixture in conftest.py (`_stub_google_trends_network`)
# replaces GoogleTrendsCollector.collect on the class for every test so the
# rest of the suite never hits the real network. These tests exist
# specifically to exercise the *real* implementation, so capture the
# original unbound function here (before any monkeypatching happens) and
# call it directly, bypassing whatever is currently patched onto the class.
_REAL_COLLECT = GoogleTrendsCollector.collect

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0">
  <channel>
    <title>Daily Search Trends</title>
    <item>
      <title>air fryer recipes</title>
      <ht:approx_traffic>5K+</ht:approx_traffic>
      <description/>
      <link>https://trends.google.com/trending/rss?geo=US</link>
      <pubDate>Mon, 10 Aug 2026 04:20:00 -0700</pubDate>
      <ht:news_item>
        <ht:news_item_title>Best air fryer recipes for 2026</ht:news_item_title>
        <ht:news_item_url>https://example.com/air-fryer</ht:news_item_url>
      </ht:news_item>
    </item>
    <item>
      <title>celebrity gossip</title>
      <ht:approx_traffic>1M+</ht:approx_traffic>
      <description/>
      <link>https://trends.google.com/trending/rss?geo=US</link>
      <pubDate>Mon, 10 Aug 2026 04:20:00 -0700</pubDate>
    </item>
  </channel>
</rss>
"""


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://trends.google.com/trending/rss")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)


class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient so no real network call is made."""

    response_text = SAMPLE_RSS
    response_status = 200

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def get(self, url: str, params: dict | None = None) -> _FakeResponse:
        return _FakeResponse(self.response_text, self.response_status)


@pytest.mark.asyncio
async def test_collect_filters_by_query_keywords(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    collector = GoogleTrendsCollector()

    items = await _REAL_COLLECT(collector, "air fryer recipes")

    assert len(items) == 1
    item = items[0]
    assert item.title == "air fryer recipes"
    assert item.source == "google_trends"
    assert item.url.startswith("https://trends.google.com/trends/explore?q=")
    assert item.metrics["approx_traffic"] == "5K+"
    assert item.metrics["approx_traffic_numeric"] == 5000
    assert item.metrics["related_articles"] == 1
    assert item.published_at is not None


@pytest.mark.asyncio
async def test_collect_requires_all_keywords_not_just_any_common_word(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test: a query sharing one generic word (e.g. "recipes")
    with an unrelated trend must NOT match — every keyword is required.
    """
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    collector = GoogleTrendsCollector()

    items = await _REAL_COLLECT(collector, "celebrity recipes")

    assert items == []


@pytest.mark.asyncio
async def test_collect_returns_empty_when_no_keyword_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Honest behavior: the daily feed isn't query-scoped, so an unrelated
    niche should legitimately surface zero items rather than fabricated ones.
    """
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    collector = GoogleTrendsCollector()

    items = await _REAL_COLLECT(collector, "underwater basket weaving")

    assert items == []


@pytest.mark.asyncio
async def test_collect_raises_collector_error_on_http_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingClient(_FakeAsyncClient):
        response_status = 503

    monkeypatch.setattr(httpx, "AsyncClient", _FailingClient)
    collector = GoogleTrendsCollector()

    with pytest.raises(CollectorError):
        await _REAL_COLLECT(collector, "anything")


@pytest.mark.asyncio
async def test_collect_raises_collector_error_on_unparseable_xml(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _MalformedClient(_FakeAsyncClient):
        response_text = "not xml at all <<<"

    monkeypatch.setattr(httpx, "AsyncClient", _MalformedClient)
    collector = GoogleTrendsCollector()

    with pytest.raises(CollectorError):
        await _REAL_COLLECT(collector, "anything")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, 0),
        ("", 0),
        ("200+", 200),
        ("5K+", 5_000),
        ("1M+", 1_000_000),
        ("2.5M+", 2_500_000),
        ("garbage", 0),
    ],
)
def test_parse_approx_traffic(raw: str | None, expected: int) -> None:
    assert _parse_approx_traffic(raw) == expected


def test_short_only_query_does_not_match_everything() -> None:
    # Niches like "AI" / "VR" previously returned True (match all) because
    # every token was filtered out as too short — that polluted rankings.
    assert _is_relevant("AI", "unrelated celebrity gossip trending today") is False
    assert _is_relevant("VR", "virtual reality headset launch news") is False
