import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.trend import Trend
from app.services import scoring
from app.services.collectors import (
    CollectedItem,
    CollectorError,
    CollectorNotConfiguredError,
    TrendCollector,
    YouTubeCollector,
)
from app.services.language import classify_trend_language
from app.services.llm_service import LLMService
from app.services.trend_similarity import is_similar_to_any, select_diverse

logger = logging.getLogger("creatoros.trends")

# How far back similar titles block a newly collected trend (freshness).
_RECENT_SIMILARITY_DAYS = 14
_SIMILARITY_THRESHOLD = 0.5
# Max new trends persisted per collect run (after English + diversity filters).
_MAX_NEW_PER_COLLECT = 10


class TrendService:
    def __init__(
        self,
        db: Session,
        collectors: list[TrendCollector] | None = None,
        llm_service: LLMService | None = None,
    ):
        self.db = db
        self.collectors: list[TrendCollector] = (
            collectors if collectors is not None else [YouTubeCollector()]
        )
        self.llm_service = llm_service or LLMService()

    def list_for_project(self, project: Project) -> list[Trend]:
        from app.core.config import get_settings

        stmt = (
            select(Trend)
            .where(
                Trend.project_id == project.id,
                # User-facing trends are English-only (language='en').
                # Legacy rows without language are included until recollected.
                (Trend.language == "en") | (Trend.language.is_(None)),
                Trend.source == "youtube",
                Trend.url.contains("/shorts/"),
            )
            .order_by(Trend.score.desc(), Trend.created_at.desc())
            .limit(get_settings().max_list_items)
        )
        return list(self.db.scalars(stmt))

    def get_owned(self, project: Project, trend_id: UUID) -> Trend:
        trend = self.db.get(Trend, trend_id)
        if trend is None or trend.project_id != project.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trend not found.",
            )
        return trend

    def select_trend(self, project: Project, trend_id: UUID) -> Trend:
        """Single-selection semantics: selecting one trend deselects the rest,
        matching the linear Trend -> Research -> Strategy -> Content pipeline.
        """
        target = self.get_owned(project, trend_id)
        stmt = select(Trend).where(
            Trend.project_id == project.id, Trend.is_selected.is_(True)
        )
        for other in self.db.scalars(stmt):
            if other.id != target.id:
                other.is_selected = False
        target.is_selected = True
        self.db.commit()
        self.db.refresh(target)
        return target

    def _recent_trend_titles(self, project: Project) -> list[str]:
        cutoff = datetime.now(tz=UTC) - timedelta(days=_RECENT_SIMILARITY_DAYS)
        stmt = select(Trend.title).where(
            Trend.project_id == project.id,
            Trend.created_at >= cutoff,
        )
        return [title for title in self.db.scalars(stmt) if title]

    async def collect(
        self, project: Project, query: str | None
    ) -> tuple[list[Trend], int, list[str], list[str]]:
        search_query = (query or project.niche or project.name or "").strip()
        if not search_query:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provide a query, or set the project's niche first.",
            )

        sources_used: list[str] = []
        warnings: list[str] = []
        collected_items: list[CollectedItem] = []

        existing_urls = {
            trend.url
            for trend in self.db.scalars(
                select(Trend).where(Trend.project_id == project.id)
            )
        }
        recent_titles = self._recent_trend_titles(project)

        for collector in self.collectors:
            try:
                # Over-fetch candidates; English/dedupe/diversity will trim.
                # Pass existing URLs so collectors can surface fresher videos.
                items = await collector.collect(
                    search_query,
                    limit=15,
                    exclude_urls=existing_urls,
                )
            except CollectorNotConfiguredError as exc:
                warnings.append(str(exc))
                continue
            except CollectorError as exc:
                logger.warning("Collector %s failed: %s", collector.source_name, exc)
                warnings.append(f"{collector.source_name} collection failed: {exc}")
                continue
            except Exception:
                # Third-party responses can be malformed in ways a collector
                # did not anticipate. Keep one bad source from taking down a
                # user's collection request, while retaining the traceback in
                # server logs for diagnosis.
                logger.exception("Collector %s failed unexpectedly", collector.source_name)
                warnings.append(
                    f"{collector.source_name} collection failed unexpectedly."
                )
                continue
            sources_used.append(collector.source_name)
            collected_items.extend(items)

        skipped_non_english = 0
        skipped_similar = 0
        skipped_existing = 0
        english_candidates: list[tuple[CollectedItem, float, str]] = []
        collector_stats: dict[str, int] = {}
        for collector in self.collectors:
            extra = getattr(collector, "last_stats", None)
            if isinstance(extra, dict):
                collector_stats.update(extra)

        youtube_results = int(collector_stats.get("youtube_results", len(collected_items)))
        shorts_kept = int(collector_stats.get("shorts_filter", len(collected_items)))
        logger.info(
            "Pipeline YouTube results: %s → Shorts filter: %s",
            youtube_results,
            shorts_kept,
        )

        for item in collected_items:
            if item.url in existing_urls:
                skipped_existing += 1
                continue

            decision = await classify_trend_language(
                title=item.title,
                description=item.description,
                default_language=item.default_language
                or (item.metrics or {}).get("default_language"),
                default_audio_language=item.default_audio_language
                or (item.metrics or {}).get("default_audio_language"),
                llm_service=self.llm_service,
            )
            if not decision.is_english or decision.language != "en":
                skipped_non_english += 1
                logger.info(
                    "English filter drop: %r method=%s reason=%s",
                    item.title,
                    decision.method,
                    decision.reason,
                )
                continue

            score = scoring.score_item(item.source, item.metrics, item.published_at)
            english_candidates.append((item, score, decision.language))

        logger.info("English filter: %s remaining", len(english_candidates))

        # Prefer spoken-English tags when ranking, but do not drop untagged
        # English Shorts — YouTube leaves defaultAudioLanguage empty on most clips.
        def _rank(row: tuple[CollectedItem, float, str]) -> tuple:
            item, score, _language = row
            audio = (item.default_audio_language or "").lower()
            default = (item.default_language or "").lower()
            has_en_audio = audio.startswith("en")
            has_en_default = default.startswith("en")
            return (has_en_audio, has_en_default, score)

        english_candidates.sort(key=_rank, reverse=True)

        after_freshness: list[tuple[CollectedItem, float, str]] = []
        skipped_fresh = 0
        for row in english_candidates:
            if is_similar_to_any(
                row[0].title, recent_titles, threshold=_SIMILARITY_THRESHOLD
            ):
                skipped_fresh += 1
                continue
            after_freshness.append(row)
        logger.info(
            "Freshness filter: %s remaining (blocked_similar_recent=%s existing_urls=%s)",
            len(after_freshness),
            skipped_fresh,
            skipped_existing,
        )

        diverse = select_diverse(
            after_freshness,
            title_getter=lambda row: row[0].title,
            limit=_MAX_NEW_PER_COLLECT,
            threshold=_SIMILARITY_THRESHOLD,
            seed_titles=None,
        )
        skipped_similar = max(0, len(after_freshness) - len(diverse))
        logger.info("Deduplication: %s remaining", len(diverse))

        scores = [score for _item, score, _language in diverse]
        logger.info(
            "Scoring: %s remaining (no min threshold; scores=%s)",
            len(diverse),
            scores,
        )
        logger.info(
            "Pipeline YouTube results=%s → Shorts filter=%s → "
            "English filter=%s → freshness filter=%s → "
            "deduplication=%s → scoring=%s",
            youtube_results,
            shorts_kept,
            len(english_candidates),
            len(after_freshness),
            len(diverse),
            len(diverse),
        )
        warnings.append(
            f"Kept {len(diverse)} English Shorts from {youtube_results} YouTube results."
        )

        new_count = 0
        for item, score, language in diverse:
            if item.url in existing_urls:
                continue
            metrics = dict(item.metrics or {})
            metrics.setdefault(
                "default_language", item.default_language
            )
            metrics.setdefault(
                "default_audio_language", item.default_audio_language
            )
            try:
                # The nested transaction makes the model-level uniqueness
                # constraint race-safe: a simultaneous collection can skip
                # only its duplicate rather than rolling back all new trends.
                with self.db.begin_nested():
                    trend = Trend(
                        project_id=project.id,
                        title=item.title[:500],
                        source=item.source,
                        url=item.url,
                        score=score,
                        metrics=metrics,
                        language=language,
                    )
                    self.db.add(trend)
                    self.db.flush()
            except IntegrityError:
                existing_urls.add(item.url)
                continue
            existing_urls.add(item.url)
            new_count += 1

        if skipped_non_english:
            warnings.append(
                f"Skipped {skipped_non_english} clip(s) that were not spoken English "
                "(YouTube tagged another language — often Hindi/other AI kids videos)."
            )
        if skipped_similar:
            warnings.append(
                f"Filtered {skipped_similar} duplicate/similar or recently seen "
                "topic(s) for freshness and diversity."
            )

        self.db.commit()

        return self.list_for_project(project), new_count, sources_used, warnings
