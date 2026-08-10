import logging
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.trend import Trend
from app.services import scoring
from app.services.collectors import (
    CollectedItem,
    CollectorError,
    CollectorNotConfiguredError,
    GoogleTrendsCollector,
    TrendCollector,
    YouTubeCollector,
)

logger = logging.getLogger("creatoros.trends")


class TrendService:
    def __init__(self, db: Session, collectors: list[TrendCollector] | None = None):
        self.db = db
        self.collectors: list[TrendCollector] = (
            collectors
            if collectors is not None
            else [GoogleTrendsCollector(), YouTubeCollector()]
        )

    def list_for_project(self, project: Project) -> list[Trend]:
        stmt = (
            select(Trend)
            .where(Trend.project_id == project.id)
            .order_by(Trend.score.desc(), Trend.created_at.desc())
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

        for collector in self.collectors:
            try:
                items = await collector.collect(search_query, limit=10)
            except CollectorNotConfiguredError as exc:
                warnings.append(str(exc))
                continue
            except CollectorError as exc:
                logger.warning("Collector %s failed: %s", collector.source_name, exc)
                warnings.append(f"{collector.source_name} collection failed: {exc}")
                continue
            sources_used.append(collector.source_name)
            collected_items.extend(items)

        existing_urls = {
            trend.url
            for trend in self.db.scalars(
                select(Trend).where(Trend.project_id == project.id)
            )
        }

        new_count = 0
        for item in collected_items:
            if item.url in existing_urls:
                continue
            score = scoring.score_item(item.source, item.metrics, item.published_at)
            trend = Trend(
                project_id=project.id,
                title=item.title[:500],
                source=item.source,
                url=item.url,
                score=score,
                metrics=item.metrics,
            )
            self.db.add(trend)
            existing_urls.add(item.url)
            new_count += 1

        self.db.commit()

        return self.list_for_project(project), new_count, sources_used, warnings
