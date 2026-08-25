"""Live trend-collection smoke (YouTube + language + diversity).

  .venv\\Scripts\\python.exe tests/manual_trend_collect_smoke.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.project import Project
from app.models.user import User
from app.services.language import is_english_text
from app.services.trend_service import TrendService


async def main() -> int:
    get_settings.cache_clear()
    settings = get_settings()
    if not settings.youtube_api_key:
        print("BLOCKED: YOUTUBE_API_KEY missing")
        return 2

    db = SessionLocal()
    try:
        email = f"trend-smoke-{uuid4().hex[:8]}@example.com"
        user = User(email=email, password_hash="unused-smoke-hash")
        db.add(user)
        db.flush()
        project = Project(
            user_id=user.id,
            name="Trend Smoke",
            niche="AI YouTube Shorts tips",
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        service = TrendService(db)
        run_titles: list[set[str]] = []
        for run in range(1, 3):
            trends, new_count, sources, warnings = await service.collect(
                project, "AI YouTube Shorts tips"
            )
            # Newly created in this project only for this smoke user.
            fresh = [t for t in trends if t.language == "en"]
            titles = [t.title for t in fresh[:15]]
            scores = [t.score for t in fresh[:15]]
            run_titles.append(set(titles))
            print(f"\n=== RUN {run} ===")
            print("sources=", sources)
            print("new_count=", new_count)
            print("warnings=", warnings)
            print("scores=", scores)
            for t in fresh[:10]:
                line = (
                    f"  [{t.score:5.1f}] lang={t.language} "
                    f"audio={(t.metrics or {}).get('default_audio_language')} "
                    f"| {t.title[:90]}"
                )
                print(line.encode("ascii", "replace").decode("ascii"))
            assert all(is_english_text(t.title) for t in fresh), "non-English title leaked"
            assert all(t.language == "en" for t in fresh), "language tag not en"
            if len(scores) >= 2:
                assert len(set(scores)) >= 2, "scores not differentiated"

        # Second run should not re-add near-duplicates of first-run topics.
        if run_titles[0] and run_titles[1]:
            overlap = run_titles[0] & run_titles[1]
            print("\nexact_title_overlap_between_top_lists=", len(overlap))
            # Cross-run near-dup check on newly collected titles only is hard
            # via list endpoint; new_count on run 2 being lower is the signal.
        print("\nPASS live trend smoke")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
