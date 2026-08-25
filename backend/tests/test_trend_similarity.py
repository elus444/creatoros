from app.services.trend_similarity import (
    is_similar_to_any,
    normalize_title,
    select_diverse,
    title_similarity,
)


def test_normalize_strips_filler_and_case() -> None:
    assert normalize_title("The Best AI Shorts Tips!") == normalize_title(
        "best ai tips shorts"
    )


def test_similar_titles_detected() -> None:
    assert title_similarity("AI Shorts growth tips", "Tips for AI Shorts growth") >= 0.5
    assert is_similar_to_any(
        "How to edit Shorts faster",
        ["Edit YouTube Shorts faster today"],
        threshold=0.5,
    )


def test_unrelated_titles_not_similar() -> None:
    assert title_similarity("Sourdough starter guide", "Budget travel Japan 2026") < 0.4


def test_select_diverse_keeps_topic_spread() -> None:
    items = [
        ("AI Shorts growth tips for beginners", 90),
        ("AI Shorts growth tips advanced", 80),
        ("Sourdough bread baking trend", 70),
        ("Budget travel packing hacks", 60),
    ]
    chosen = select_diverse(
        items,
        title_getter=lambda row: row[0],
        limit=3,
        threshold=0.5,
        seed_titles=["AI Shorts growth tips for beginners yesterday"],
    )
    titles = [row[0] for row in chosen]
    # Seed blocks the near-duplicate AI cluster; other topics remain.
    assert not any("AI Shorts" in title for title in titles)
    assert "Sourdough bread baking trend" in titles
    assert "Budget travel packing hacks" in titles
