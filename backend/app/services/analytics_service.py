"""Analytics aggregation + Analytics/Coach agent orchestration (M6).

Owns metric ingest, chart-ready series, top content, and AI coaching.
Does not invent performance numbers — only aggregates stored rows and
interprets them via llm_service-backed agents.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID
import logging

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent_run import AgentRun
from app.models.analytics_daily import AnalyticsDaily
from app.models.content import Content, PublishStatus
from app.models.project import Project
from app.models.trend import Trend
from app.models.user import User
from app.schemas.analytics import AnalyticsIngestRequest
from app.services.agents.analytics_agent import AnalyticsAgent
from app.services.agents.base import AgentAttempt, AgentExecutionError
from app.services.agents.coach_agent import CoachAgent
from app.services.llm_service import LLMService
from app.services.project_service import ProjectService
from app.core import redis as redis_module

logger = logging.getLogger("creatoros.analytics")

# Minimum distinct content pieces with metrics before Coach may run.
MIN_CONTENT_FOR_COACH = 3
_YT_SYNC_PREFIX = "analytics:yt-sync:"
_YT_SYNC_TTL_SECONDS = 120


def compute_engagement_rate(views: int, likes: int, comments: int) -> Decimal:
    """Authoritative engagement rate: (likes + comments) / views * 100."""
    if views <= 0:
        return Decimal("0.0000")
    rate = (Decimal(likes + comments) / Decimal(views)) * Decimal(100)
    return rate.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


class AnalyticsService:
    def __init__(self, db: Session, llm_service: LLMService | None = None):
        self.db = db
        self.projects = ProjectService(db)
        self.llm_service = llm_service or LLMService()
        self.analytics_agent = AnalyticsAgent(self.llm_service)
        self.coach_agent = CoachAgent(self.llm_service)

    def get_owned_content(self, user: User, content_id: UUID) -> Content:
        content = self.db.get(Content, content_id)
        if content is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Content not found."
            )
        project = self.db.get(Project, content.project_id)
        if project is None or project.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Content not found."
            )
        return content

    def ingest(self, user: User, payload: AnalyticsIngestRequest) -> AnalyticsDaily:
        content = self.get_owned_content(user, payload.content_id)
        return self.upsert_snapshot(
            content,
            views=payload.views,
            likes=payload.likes,
            comments=payload.comments,
            day=payload.date,
        )

    def upsert_snapshot(
        self,
        content: Content,
        *,
        views: int,
        likes: int,
        comments: int,
        day: date | None = None,
    ) -> AnalyticsDaily:
        snapshot_day = day or date.today()
        rate = compute_engagement_rate(views, likes, comments)
        existing = self.db.scalars(
            select(AnalyticsDaily).where(
                AnalyticsDaily.content_id == content.id,
                AnalyticsDaily.date == snapshot_day,
            )
        ).first()
        if existing is None:
            row = AnalyticsDaily(
                content_id=content.id,
                views=views,
                likes=likes,
                comments=comments,
                engagement_rate=rate,
                date=snapshot_day,
            )
            self.db.add(row)
        else:
            existing.views = views
            existing.likes = likes
            existing.comments = comments
            existing.engagement_rate = rate
            row = existing
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_snapshots(self, content: Content) -> int:
        rows = list(
            self.db.scalars(
                select(AnalyticsDaily).where(AnalyticsDaily.content_id == content.id)
            ).all()
        )
        if not rows:
            return 0
        for row in rows:
            self.db.delete(row)
        self.db.commit()
        return len(rows)

    def _published_youtube_content(self, project_id: UUID) -> list[Content]:
        return list(
            self.db.scalars(
                select(Content).where(
                    Content.project_id == project_id,
                    Content.publish_status == PublishStatus.PUBLISHED,
                    Content.youtube_video_id.isnot(None),
                )
            ).all()
        )

    def _youtube_sync_fresh(self, project_id: UUID) -> bool:
        try:
            return bool(redis_module.redis_client.get(f"{_YT_SYNC_PREFIX}{project_id}"))
        except Exception:
            return False

    def _mark_youtube_synced(self, project_id: UUID) -> None:
        try:
            redis_module.redis_client.setex(
                f"{_YT_SYNC_PREFIX}{project_id}", _YT_SYNC_TTL_SECONDS, "1"
            )
        except Exception:
            logger.warning("Could not store YouTube analytics sync cooldown")

    def sync_from_youtube(
        self, user: User, project_id: UUID, *, force: bool = False
    ) -> dict:
        """Pull live views/likes/comments for published Shorts. Never invents."""
        from app.services.youtube_service import YouTubeService

        project = self.projects.get_owned(user, project_id)
        items = [
            row
            for row in self._published_youtube_content(project.id)
            if row.youtube_video_id
        ]
        if not items:
            return {
                "synced": 0,
                "published": 0,
                "skipped": False,
                "cleared": 0,
                "message": "No published YouTube videos in this project yet.",
            }
        if not force and self._youtube_sync_fresh(project.id):
            return {
                "synced": 0,
                "published": len(items),
                "skipped": True,
                "cleared": 0,
                "message": "Using recently synced YouTube statistics.",
            }
        stats = YouTubeService(self.db).fetch_video_statistics(
            user, [row.youtube_video_id for row in items if row.youtube_video_id]
        )
        synced = 0
        cleared = 0
        for row in items:
            video_id = row.youtube_video_id
            snapshot = stats.get(video_id) if video_id else None
            if snapshot is None:
                cleared += self.delete_snapshots(row)
                continue
            self.upsert_snapshot(
                row,
                views=snapshot["views"],
                likes=snapshot["likes"],
                comments=snapshot["comments"],
            )
            synced += 1
        self._mark_youtube_synced(project.id)
        if cleared and not synced:
            message = (
                "YouTube no longer lists these videos, so the previous report "
                "was cleared. Publish a new Short to see performance again."
            )
        elif synced:
            message = f"Updated {synced} of {len(items)} published videos from YouTube."
        else:
            message = "YouTube has not returned statistics for these videos yet."
        return {
            "synced": synced,
            "published": len(items),
            "skipped": False,
            "cleared": cleared,
            "message": message,
        }

    def _sync_youtube_quiet(self, user: User, project_id: UUID) -> str | None:
        if not self._published_youtube_content(project_id):
            return None
        try:
            self.sync_from_youtube(user, project_id, force=True)
            return None
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else None
            logger.warning("YouTube analytics sync skipped: %s", detail)
            return detail
        except Exception:
            logger.exception("YouTube analytics sync failed for project %s", project_id)
            return "Could not refresh YouTube statistics."

    def project_summary(
        self, user: User, project_id: UUID, range_days: int = 30
    ) -> dict:
        project = self.projects.get_owned(user, project_id)
        range_days = _clamp_range(range_days)
        sync_error = self._sync_youtube_quiet(user, project.id)
        start = date.today() - timedelta(days=range_days - 1)
        rows = self._project_rows(project.id, start)
        return self._build_project_summary(
            project, range_days, rows, sync_error=sync_error
        )

    def content_summary(self, user: User, content_id: UUID, range_days: int = 90) -> dict:
        content = self.get_owned_content(user, content_id)
        range_days = _clamp_range(range_days)
        start = date.today() - timedelta(days=range_days - 1)
        rows = self.db.scalars(
            select(AnalyticsDaily)
            .where(
                AnalyticsDaily.content_id == content.id,
                AnalyticsDaily.date >= start,
            )
            .order_by(AnalyticsDaily.date.asc())
        ).all()
        series = _series_from_rows(rows)
        totals = _totals_from_rows(rows)
        return {
            "content_id": content.id,
            "project_id": content.project_id,
            "totals": totals,
            "series": series,
            "has_data": len(rows) > 0,
        }

    async def run_coach(self, user: User, project_id: UUID, range_days: int = 30) -> dict:
        project = self.projects.get_owned(user, project_id)
        range_days = _clamp_range(range_days)
        start = date.today() - timedelta(days=range_days - 1)
        rows = self._project_rows(project.id, start)
        summary = self._build_project_summary(project, range_days, rows)

        if summary["totals"]["content_with_metrics"] < MIN_CONTENT_FOR_COACH:
            return {
                "project_id": project.id,
                "status": "insufficient_data",
                "message": (
                    "Not enough performance data yet. Publish a few pieces of "
                    "content and collect metrics for at least "
                    f"{MIN_CONTENT_FOR_COACH} content items before generating "
                    "reliable coach recommendations."
                ),
                "analytics": None,
                "recommendations": [],
                "summary": None,
                "confidence": None,
            }

        agent_input = self._analytics_agent_input(project, summary, rows)
        try:
            analytics_result = await self._run_agent(
                agent=self.analytics_agent,
                input_data=agent_input,
                project_id=project.id,
            )
        except AgentExecutionError as exc:
            return {
                "project_id": project.id,
                "status": "failed",
                "message": str(exc),
                "analytics": None,
                "recommendations": [],
                "summary": None,
                "confidence": None,
            }

        coach_input = {
            "niche": project.niche,
            "audience": project.audience,
            "brand_voice": project.brand_voice,
            "totals": summary["totals"],
            "top_content": summary["top_content"],
            "analytics_insights": analytics_result,
            "recent_content": self._recent_content_context(project.id),
        }
        try:
            coach_result = await self._run_agent(
                agent=self.coach_agent,
                input_data=coach_input,
                project_id=project.id,
            )
        except AgentExecutionError as exc:
            return {
                "project_id": project.id,
                "status": "failed",
                "message": str(exc),
                "analytics": analytics_result,
                "recommendations": [],
                "summary": None,
                "confidence": analytics_result.get("confidence"),
            }

        return {
            "project_id": project.id,
            "status": "ready",
            "message": None,
            "analytics": analytics_result,
            "recommendations": coach_result.get("recommendations") or [],
            "summary": coach_result.get("summary"),
            "confidence": analytics_result.get("confidence"),
        }

    def _project_rows(self, project_id: UUID, start: date) -> list[AnalyticsDaily]:
        return list(
            self.db.scalars(
                select(AnalyticsDaily)
                .join(Content, AnalyticsDaily.content_id == Content.id)
                .where(Content.project_id == project_id, AnalyticsDaily.date >= start)
                .order_by(AnalyticsDaily.date.asc())
            ).all()
        )

    def _build_project_summary(
        self,
        project: Project,
        range_days: int,
        rows: list[AnalyticsDaily],
        *,
        sync_error: str | None = None,
    ) -> dict:
        series = _series_from_rows(rows)
        totals = _totals_from_rows(rows)
        top_content = self._top_content(project.id, rows)
        published_live = {
            row.content_id for row in rows
        }
        published_count = len(published_live)
        return {
            "project_id": project.id,
            "range_days": range_days,
            "totals": totals,
            "series": series,
            "top_content": top_content,
            "has_data": len(rows) > 0,
            "published_count": published_count,
            "sync_error": sync_error,
        }

    def _top_content(
        self, project_id: UUID, rows: list[AnalyticsDaily], limit: int = 5
    ) -> list[dict]:
        by_content: dict[UUID, dict] = {}
        for row in rows:
            bucket = by_content.setdefault(
                row.content_id,
                {
                    "content_id": row.content_id,
                    "views": 0,
                    "likes": 0,
                    "comments": 0,
                    "engagement_sum": Decimal(0),
                    "days": 0,
                },
            )
            bucket["views"] += row.views
            bucket["likes"] += row.likes
            bucket["comments"] += row.comments
            bucket["engagement_sum"] += Decimal(row.engagement_rate)
            bucket["days"] += 1

        ranked = sorted(by_content.values(), key=lambda item: item["views"], reverse=True)
        results: list[dict] = []
        for item in ranked[:limit]:
            content = self.db.get(Content, item["content_id"])
            trend = self.db.get(Trend, content.trend_id) if content else None
            titles = (content.titles or []) if content else []
            title = titles[0] if titles else (trend.title if trend else "Untitled")
            days = max(item["days"], 1)
            results.append(
                {
                    "content_id": item["content_id"],
                    "title": title,
                    "trend_title": trend.title if trend else None,
                    "views": item["views"],
                    "likes": item["likes"],
                    "comments": item["comments"],
                    "engagement_rate": float(
                        (item["engagement_sum"] / Decimal(days)).quantize(
                            Decimal("0.0001"), rounding=ROUND_HALF_UP
                        )
                    ),
                }
            )
        return results

    def _analytics_agent_input(
        self, project: Project, summary: dict, rows: list[AnalyticsDaily]
    ) -> dict:
        content_rows = []
        for item in summary["top_content"]:
            content = self.db.get(Content, item["content_id"])
            strategy = (content.strategy or {}) if content else {}
            content_rows.append(
                {
                    **item,
                    "hooks": strategy.get("hooks") or [],
                    "angle": strategy.get("angle"),
                    "titles": (content.titles or []) if content else [],
                    "status": content.status if content else None,
                    "created_at": content.created_at.isoformat() if content else None,
                }
            )
        series = summary["series"]
        series_summary = {
            "points": len(series),
            "first_date": series[0]["date"].isoformat() if series else None,
            "last_date": series[-1]["date"].isoformat() if series else None,
            "peak_views": max((p["views"] for p in series), default=0),
        }
        return {
            "niche": project.niche,
            "audience": project.audience,
            "totals": summary["totals"],
            "top_content": summary["top_content"],
            "content_rows": content_rows,
            "series_summary": series_summary,
            "daily_row_count": len(rows),
        }

    def _recent_content_context(self, project_id: UUID, limit: int = 8) -> list[dict]:
        rows = self.db.scalars(
            select(Content)
            .where(Content.project_id == project_id)
            .order_by(Content.created_at.desc())
            .limit(limit)
        ).all()
        out = []
        for content in rows:
            strategy = content.strategy or {}
            titles = content.titles or []
            out.append(
                {
                    "content_id": str(content.id),
                    "title": titles[0] if titles else None,
                    "angle": strategy.get("angle"),
                    "hooks": strategy.get("hooks") or [],
                    "status": content.status,
                }
            )
        return out

    async def _run_agent(self, *, agent, input_data: dict, project_id: UUID) -> dict:
        try:
            result = await agent.run(input_data)
        except AgentExecutionError as exc:
            for attempt in exc.attempts:
                self._log_attempt(
                    agent_name=agent.name,
                    input_data=input_data,
                    attempt=attempt,
                    project_id=project_id,
                )
            self.db.commit()
            raise
        for attempt in result.attempts:
            self._log_attempt(
                agent_name=agent.name,
                input_data=input_data,
                attempt=attempt,
                project_id=project_id,
            )
        self.db.commit()
        return result.output.model_dump()

    def _log_attempt(
        self,
        *,
        agent_name: str,
        input_data: dict,
        attempt: AgentAttempt,
        project_id: UUID,
        content_id: UUID | None = None,
    ) -> None:
        run = AgentRun(
            content_id=content_id,
            project_id=project_id,
            agent_name=agent_name,
            attempt=attempt.attempt,
            input=_json_safe(input_data),
            output=_json_safe(attempt.output) if attempt.output is not None else None,
            status=attempt.status,
            error=attempt.error,
            tokens=(
                {
                    "prompt": attempt.prompt_tokens,
                    "completion": attempt.completion_tokens,
                    "total": attempt.total_tokens,
                }
                if attempt.total_tokens is not None
                else None
            ),
        )
        self.db.add(run)


def _json_safe(value):
    """Make nested structures JSON-serializable for agent_runs storage."""
    return json.loads(json.dumps(value, default=_json_default))


def _json_default(value):
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _clamp_range(range_days: int) -> int:
    if range_days not in (7, 30, 90):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="range_days must be 7, 30, or 90.",
        )
    return range_days


def _series_from_rows(rows: list[AnalyticsDaily]) -> list[dict]:
    by_date: dict[date, dict] = {}
    for row in rows:
        bucket = by_date.setdefault(
            row.date,
            {
                "date": row.date,
                "views": 0,
                "likes": 0,
                "comments": 0,
                "engagement_sum": Decimal(0),
                "count": 0,
            },
        )
        bucket["views"] += row.views
        bucket["likes"] += row.likes
        bucket["comments"] += row.comments
        bucket["engagement_sum"] += Decimal(row.engagement_rate)
        bucket["count"] += 1

    series = []
    for day in sorted(by_date):
        bucket = by_date[day]
        avg = (
            bucket["engagement_sum"] / Decimal(bucket["count"])
            if bucket["count"]
            else Decimal(0)
        )
        series.append(
            {
                "date": day,
                "views": bucket["views"],
                "likes": bucket["likes"],
                "comments": bucket["comments"],
                "engagement_rate": float(
                    avg.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                ),
            }
        )
    return series


def _totals_from_rows(rows: list[AnalyticsDaily]) -> dict:
    views = sum(r.views for r in rows)
    likes = sum(r.likes for r in rows)
    comments = sum(r.comments for r in rows)
    content_ids = {r.content_id for r in rows}
    if rows:
        avg = sum((Decimal(r.engagement_rate) for r in rows), Decimal(0)) / Decimal(
            len(rows)
        )
        avg_f = float(avg.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
    else:
        avg_f = 0.0
    return {
        "views": views,
        "likes": likes,
        "comments": comments,
        "average_engagement_rate": avg_f,
        "content_with_metrics": len(content_ids),
        "daily_rows": len(rows),
    }
