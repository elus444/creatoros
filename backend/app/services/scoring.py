"""Trend scoring — intentionally independent of any collector (Constitution §19).

Favors *current growth / engagement velocity* over raw lifetime popularity:

    score = min(100, ln(1 + growth_signal) * 10 * recency_weight)

YouTube growth_signal blends views-per-day, engagement rate, and absolute
engagement so a fresh mid-view video can outrank a stale mega-hit.
Google Trends still uses traffic + related articles (no velocity available).
"""

import math
from datetime import UTC, datetime

_HALF_LIFE_DAYS = 10.0
_MIN_RECENCY_WEIGHT = 0.25
_UNKNOWN_AGE_WEIGHT = 0.55


def _age_days(published_at: datetime | None) -> float | None:
    if published_at is None:
        return None
    aware = (
        published_at
        if published_at.tzinfo is not None
        else published_at.replace(tzinfo=UTC)
    )
    return max((datetime.now(tz=UTC) - aware).total_seconds() / 86400, 0.0)


def _engagement_signal(source: str, metrics: dict, published_at: datetime | None) -> float:
    if source == "youtube":
        views = float(metrics.get("views", 0) or 0)
        likes = float(metrics.get("likes", 0) or 0)
        comments = float(metrics.get("comments", 0) or 0)
        age = _age_days(published_at)
        # Floor at ~2 hours so brand-new videos aren't infinitely boosted.
        age_for_velocity = max(age if age is not None else 3.0, 2.0 / 24.0)
        views_per_day = views / age_for_velocity
        engagement_rate = (likes + comments * 2.0) / max(views, 1.0)
        # Growth-first blend: velocity dominates; rate rewards sticky videos;
        # absolute likes/comments break ties without letting pure popularity win.
        return (
            views_per_day / 35.0
            + engagement_rate * min(views, 250_000) / 25.0
            + likes * 1.5
            + comments * 2.5
        )
    if source == "google_trends":
        # Google's RSS feed only exposes a rough "approx_traffic" bucket
        # (e.g. "5K+") and related news article count — no likes/comments
        # exist for a search trend, so we don't invent them.
        return (
            float(metrics.get("approx_traffic_numeric", 0) or 0)
            + float(metrics.get("related_articles", 0) or 0) * 500
        )
    # Unknown/future source: generic fallback so the scorer never crashes
    # when a new collector is added before scoring is taught about it.
    return sum(value for value in metrics.values() if isinstance(value, (int, float)))


def _recency_weight(published_at: datetime | None) -> float:
    if published_at is None:
        return _UNKNOWN_AGE_WEIGHT
    age_days = _age_days(published_at)
    if age_days is None:
        return _UNKNOWN_AGE_WEIGHT
    return max(_MIN_RECENCY_WEIGHT, 1.0 - (age_days / _HALF_LIFE_DAYS))


def score_item(source: str, metrics: dict, published_at: datetime | None) -> float:
    engagement = max(0.0, _engagement_signal(source, metrics, published_at))
    recency_weight = _recency_weight(published_at)
    raw_score = math.log1p(engagement) * 10 * recency_weight
    return round(min(100.0, raw_score), 2)
