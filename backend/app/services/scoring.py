"""Trend scoring — intentionally independent of any collector (Constitution §19).

A trend's score approximates "how hot is this right now" from whatever raw
engagement signals its source captured, discounted by recency. This is a
transparent, deterministic heuristic — never a black box or random number:

    score = min(100, ln(1 + engagement) * 10 * recency_weight)

`engagement` is a source-specific weighted sum of the collector's raw
metrics. `recency_weight` decays linearly from 1.0 (brand new) down to a
floor of 0.3 (14+ days old), so older items are down-ranked but never zeroed.
"""

import math
from datetime import UTC, datetime

_HALF_LIFE_DAYS = 14.0
_MIN_RECENCY_WEIGHT = 0.3
_UNKNOWN_AGE_WEIGHT = 0.6


def _engagement_signal(source: str, metrics: dict) -> float:
    if source == "youtube":
        return (
            float(metrics.get("views", 0)) / 50
            + float(metrics.get("likes", 0)) * 3
            + float(metrics.get("comments", 0)) * 2
        )
    if source == "google_trends":
        # Google's RSS feed only exposes a rough "approx_traffic" bucket
        # (e.g. "5K+") and related news article count — no likes/comments
        # exist for a search trend, so we don't invent them.
        return (
            float(metrics.get("approx_traffic_numeric", 0))
            + float(metrics.get("related_articles", 0)) * 500
        )
    # Unknown/future source: generic fallback so the scorer never crashes
    # when a new collector is added before scoring is taught about it.
    return sum(value for value in metrics.values() if isinstance(value, (int, float)))


def _recency_weight(published_at: datetime | None) -> float:
    if published_at is None:
        return _UNKNOWN_AGE_WEIGHT
    # Collectors sometimes yield naive datetimes (e.g. RSS pubDate without TZ).
    # Treat those as UTC rather than crashing score_item / trend collect.
    aware = (
        published_at
        if published_at.tzinfo is not None
        else published_at.replace(tzinfo=UTC)
    )
    age_days = (datetime.now(tz=UTC) - aware).total_seconds() / 86400
    return max(_MIN_RECENCY_WEIGHT, 1.0 - (age_days / _HALF_LIFE_DAYS))


def score_item(source: str, metrics: dict, published_at: datetime | None) -> float:
    engagement = max(0.0, _engagement_signal(source, metrics))
    recency_weight = _recency_weight(published_at)
    raw_score = math.log1p(engagement) * 10 * recency_weight
    return round(min(100.0, raw_score), 2)
