"""Real YouTube Shorts collect — prints remaining counts after each filter.

Does not write to the database. Uses the live YOUTUBE_API_KEY from .env.
Never fabricates results.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Allow `python tests/manual_shorts_collect_debug.py` from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.services import scoring
from app.services.collectors.youtube_collector import YouTubeCollector
from app.services.language import classify_trend_language
from app.services.llm_service import LLMService
from app.services.trend_similarity import is_similar_to_any, select_diverse


async def run(query: str) -> dict[str, int]:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = get_settings()
    if not settings.youtube_api_key:
        raise SystemExit("YOUTUBE_API_KEY is not set; cannot run a real collection.")

    collector = YouTubeCollector()
    items = await collector.collect(query, limit=15)
    stats = dict(collector.last_stats)
    youtube_results = int(stats.get("youtube_results", 0))
    shorts_kept = int(stats.get("shorts_filter", len(items)))

    llm = LLMService() if settings.gemini_api_key else None
    english: list = []
    for item in items:
        decision = await classify_trend_language(
            title=item.title,
            description=item.description,
            default_language=item.default_language,
            default_audio_language=item.default_audio_language,
            llm_service=llm,
        )
        if decision.is_english and decision.language == "en":
            score = scoring.score_item(item.source, item.metrics, item.published_at)
            english.append((item, score, decision.language))
        else:
            title = item.title.encode("ascii", "replace").decode("ascii")
            print(
                f"  English drop: {title!r} "
                f"method={decision.method} reason={decision.reason}"
            )

    after_freshness = [
        row
        for row in english
        if not is_similar_to_any(row[0].title, [], threshold=0.5)
    ]
    diverse = select_diverse(
        after_freshness,
        title_getter=lambda row: row[0].title,
        limit=10,
        threshold=0.5,
        seed_titles=None,
    )
    scores = [score for _item, score, _lang in diverse]

    funnel = {
        "youtube_results": youtube_results,
        "shorts_filter": shorts_kept,
        "english_filter": len(english),
        "freshness_filter": len(after_freshness),
        "deduplication": len(diverse),
        "scoring": len(diverse),
    }
    print()
    print(f"Query: {query!r}")
    print(f"Search window days: {stats.get('search_window_days')}")
    print(f"Details fetched: {stats.get('details_fetched')}")
    print(f"Age-restricted dropped: {stats.get('age_restricted_dropped')}")
    print(f"Unparsed duration: {stats.get('duration_unparsed')}")
    print(f"Long-form dropped: {stats.get('long_form_dropped')}")
    print()
    print("YouTube results     ", funnel["youtube_results"])
    print("→ Shorts filter     ", funnel["shorts_filter"])
    print("→ English filter    ", funnel["english_filter"])
    print("→ freshness filter  ", funnel["freshness_filter"])
    print("→ deduplication     ", funnel["deduplication"])
    print("→ scoring           ", funnel["scoring"], scores)
    print()
    for item, score, _lang in diverse:
        title = item.title.encode("ascii", "replace").decode("ascii")
        print(f"  {score:5.1f}  {item.metrics.get('duration_seconds')}s  {title}")
        print(f"         {item.url}")
    return funnel


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="?", default="kids counting")
    args = parser.parse_args()
    asyncio.run(run(args.query))
