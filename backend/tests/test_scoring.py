from datetime import UTC, datetime, timedelta

from app.services import scoring


def test_more_engagement_scores_higher() -> None:
    now = datetime.now(tz=UTC)
    low = scoring.score_item("youtube", {"views": 500, "likes": 5, "comments": 1}, now)
    high = scoring.score_item(
        "youtube", {"views": 500_000, "likes": 4_000, "comments": 400}, now
    )
    assert high > low


def test_older_items_score_lower_than_fresh_with_same_engagement() -> None:
    now = datetime.now(tz=UTC)
    metrics = {"views": 100_000, "likes": 1_000, "comments": 100}
    fresh = scoring.score_item("youtube", metrics, now)
    old = scoring.score_item("youtube", metrics, now - timedelta(days=20))
    assert fresh > old


def test_score_is_capped_at_100() -> None:
    now = datetime.now(tz=UTC)
    score = scoring.score_item(
        "youtube", {"views": 100_000_000, "likes": 5_000_000, "comments": 1_000_000}, now
    )
    assert score <= 100.0


def test_google_trends_more_traffic_and_articles_scores_higher() -> None:
    now = datetime.now(tz=UTC)
    low = scoring.score_item(
        "google_trends",
        {"approx_traffic": "100+", "approx_traffic_numeric": 100, "related_articles": 0},
        now,
    )
    high = scoring.score_item(
        "google_trends",
        {
            "approx_traffic": "1M+",
            "approx_traffic_numeric": 1_000_000,
            "related_articles": 5,
        },
        now,
    )
    assert high > low


def test_google_trends_missing_metrics_scores_honestly_not_fabricated() -> None:
    score = scoring.score_item("google_trends", {}, datetime.now(tz=UTC))
    assert score == 0.0


def test_unknown_source_falls_back_to_generic_signal() -> None:
    score = scoring.score_item("tiktok", {"shares": 100, "likes": 50}, None)
    assert score >= 0.0


def test_missing_published_at_uses_neutral_weight() -> None:
    score_with_date = scoring.score_item(
        "youtube", {"views": 10_000, "likes": 100, "comments": 10}, datetime.now(tz=UTC)
    )
    score_without_date = scoring.score_item(
        "youtube", {"views": 10_000, "likes": 100, "comments": 10}, None
    )
    assert score_without_date > 0
    assert score_without_date != score_with_date


def test_naive_published_at_does_not_crash_scoring() -> None:
    # RSS dates can arrive without tzinfo; scoring must treat them as UTC.
    naive = datetime(2026, 8, 10, 12, 0, 0)  # intentionally naive (no tzinfo)
    score = scoring.score_item(
        "youtube", {"views": 10_000, "likes": 100, "comments": 10}, naive
    )
    assert score > 0
