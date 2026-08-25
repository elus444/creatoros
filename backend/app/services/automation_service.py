"""n8n automation orchestration (M5).

Triggers existing TrendService / ContentService — never duplicates collectors,
scoring, agents, or prompts. Long-running work is queued in Redis and executed
in a background asyncio task with its own DB session.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.content import Content
from app.models.project import Project
from app.models.trend import Trend
from app.models.user import User
from app.services.analytics_service import AnalyticsService
from app.services.content_service import ContentService
from app.services.job_store import JobStore
from app.services.notification_service import notify_job_event
from app.services.project_service import ProjectService
from app.services.trend_service import TrendService

logger = logging.getLogger("creatoros.automation")


class AutomationService:
    def __init__(self, db: Session, job_store: JobStore | None = None):
        self.db = db
        self.jobs = job_store or JobStore()
        self.projects = ProjectService(db)
        self.trends = TrendService(db)
        self.content = ContentService(db)

    def get_project(self, project_id: UUID) -> Project:
        project = self.db.get(Project, project_id)
        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found."
            )
        return project

    def enqueue_trend_collect(
        self,
        *,
        project_id: UUID,
        query: str | None,
        idempotency_key: str | None,
        background_tasks: BackgroundTasks,
    ) -> dict:
        project = self.get_project(project_id)
        job = self.jobs.create(
            kind="trends.collect",
            payload={
                "project_id": str(project.id),
                "query": query,
                "user_id": str(project.user_id),
            },
            idempotency_key=idempotency_key,
        )
        if job.get("idempotent_replay"):
            return job
        background_tasks.add_task(self._run_trend_collect, job["job_id"])
        return job

    def enqueue_content_generate(
        self,
        *,
        project_id: UUID,
        trend_id: UUID | None,
        idempotency_key: str | None,
        background_tasks: BackgroundTasks,
    ) -> dict:
        project = self.get_project(project_id)
        trend = self._resolve_trend(project, trend_id)
        # Ensure ContentService.generate's select requirement is satisfied
        # without forcing n8n to call the user-facing select endpoint first.
        if not trend.is_selected:
            self.trends.select_trend(project, trend.id)

        job = self.jobs.create(
            kind="content.generate",
            payload={
                "project_id": str(project.id),
                "trend_id": str(trend.id),
                "user_id": str(project.user_id),
            },
            idempotency_key=idempotency_key,
        )
        if job.get("idempotent_replay"):
            return job
        background_tasks.add_task(self._run_content_generate, job["job_id"])
        return job

    def get_job(self, job_id: str) -> dict:
        job = self.jobs.get(job_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Job not found."
            )
        return job

    def resolve_content_owner(self, content_id: UUID) -> tuple[Content, User]:
        """Resolve content + its owning user without a JWT.

        Automation calls authenticate with the shared secret, not a user
        session, so there is no `current_user` to check ownership against.
        Instead we derive the owner from content -> project -> user, the
        same relationship `ContentService.get_owned_content` checks against
        a JWT user — this just walks it the other direction.
        """
        content = self.db.get(Content, content_id)
        if content is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Content not found."
            )
        project = self.db.get(Project, content.project_id)
        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Content not found."
            )
        user = self.db.get(User, project.user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Content owner not found."
            )
        return content, user

    def enqueue_publish(
        self,
        *,
        content_id: UUID,
        idempotency_key: str | None,
        background_tasks: BackgroundTasks,
    ) -> dict:
        content, user = self.resolve_content_owner(content_id)
        job = self.jobs.create(
            kind="content.publish",
            payload={
                "content_id": str(content.id),
                "project_id": str(content.project_id),
                "user_id": str(user.id),
            },
            idempotency_key=idempotency_key,
        )
        if job.get("idempotent_replay"):
            return job
        background_tasks.add_task(self._run_publish, job["job_id"])
        return job

    def enqueue_coach(
        self,
        *,
        project_id: UUID,
        range_days: int,
        idempotency_key: str | None,
        background_tasks: BackgroundTasks,
    ) -> dict:
        project = self.get_project(project_id)
        job = self.jobs.create(
            kind="analytics.coach",
            payload={
                "project_id": str(project.id),
                "range_days": range_days,
                "user_id": str(project.user_id),
            },
            idempotency_key=idempotency_key,
        )
        if job.get("idempotent_replay"):
            return job
        background_tasks.add_task(self._run_coach, job["job_id"])
        return job

    def ingest_analytics(self, payload) -> Content:
        """Synchronous — a metrics upsert is fast and has no reason to be
        a background job; n8n gets the result in the same response.
        Returns the ORM row directly so the route can serialize it with
        AnalyticsDailyPublic.model_validate(row, from_attributes=True).
        """
        content, user = self.resolve_content_owner(payload.content_id)
        return AnalyticsService(self.db).upsert_snapshot(
            content,
            views=payload.views,
            likes=payload.likes,
            comments=payload.comments,
            day=payload.date,
        )

    def status_snapshot(self, user: User) -> dict:
        # The app UI is user-authenticated, not operator-authenticated. Jobs
        # contain content IDs and failures, so never show one creator another
        # creator's automation metadata.
        recent = [
            job
            for job in self.jobs.recent(limit=50)
            if job.get("payload", {}).get("user_id") == str(user.id)
        ][:10]
        return {
            "automation_configured": True,
            "recent_jobs": [self.public_job(job) for job in recent],
        }

    def _resolve_trend(self, project: Project, trend_id: UUID | None) -> Trend:
        if trend_id is not None:
            return self.trends.get_owned(project, trend_id)
        # Daily workflow: generate from the current top-ranked trend.
        top = self.db.scalars(
            select(Trend)
            .where(Trend.project_id == project.id)
            .order_by(Trend.score.desc(), Trend.created_at.desc())
            .limit(1)
        ).first()
        if top is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No trends available for this project. Collect trends first.",
            )
        return top

    async def _run_trend_collect(self, job_id: str) -> None:
        db = SessionLocal()
        project_id: str | None = None
        try:
            self.jobs.update(job_id, status="running")
            job = self.jobs.get(job_id)
            assert job is not None
            payload = job["payload"]
            project_id = payload.get("project_id")
            project = db.get(Project, UUID(payload["project_id"]))
            if project is None:
                raise RuntimeError("Project disappeared before collect ran.")
            trends, collected, sources_used, warnings = await TrendService(db).collect(
                project, payload.get("query")
            )
            result = {
                "collected": collected,
                "sources_used": sources_used,
                "warnings": warnings,
                "trend_count": len(trends),
                "top_trend_id": str(trends[0].id) if trends else None,
            }
            self.jobs.update(job_id, status="completed", result=result)
            await notify_job_event(
                event="trends.collect.completed",
                job_id=job_id,
                kind="trends.collect",
                status="completed",
                project_id=project_id,
                result=result,
            )
        except Exception as exc:
            logger.exception("Automation trend collect failed job_id=%s", job_id)
            self.jobs.update(job_id, status="failed", error=str(exc))
            await notify_job_event(
                event="trends.collect.failed",
                job_id=job_id,
                kind="trends.collect",
                status="failed",
                project_id=project_id,
                error=str(exc),
            )
        finally:
            db.close()

    async def _run_content_generate(self, job_id: str) -> None:
        db = SessionLocal()
        project_id: str | None = None
        try:
            self.jobs.update(job_id, status="running")
            job = self.jobs.get(job_id)
            assert job is not None
            payload = job["payload"]
            project_id = payload.get("project_id")
            user = db.get(User, UUID(payload["user_id"]))
            if user is None:
                raise RuntimeError("Project owner disappeared before generate ran.")
            content = await ContentService(db).generate(
                user, UUID(payload["trend_id"])
            )
            result = {
                "content_id": str(content.id),
                "status": content.status,
                "trend_id": str(content.trend_id),
            }
            self.jobs.update(
                job_id, status="completed", content_id=str(content.id), result=result
            )
            await notify_job_event(
                event="content.generate.completed",
                job_id=job_id,
                kind="content.generate",
                status="completed",
                project_id=project_id,
                content_id=str(content.id),
                result=result,
            )
        except Exception as exc:
            # ContentService raises HTTPException for agent failures — surface
            # the detail string without leaving the job stuck in running.
            detail = getattr(exc, "detail", None)
            if isinstance(detail, dict):
                message = detail.get("message") or str(exc)
            else:
                message = str(detail or exc)
            logger.exception("Automation content generate failed job_id=%s", job_id)
            self.jobs.update(job_id, status="failed", error=message)
            await notify_job_event(
                event="content.generate.failed",
                job_id=job_id,
                kind="content.generate",
                status="failed",
                project_id=project_id,
                error=message,
            )
        finally:
            db.close()

    async def _run_publish(self, job_id: str) -> None:
        from app.services.youtube_service import YouTubeService

        db = SessionLocal()
        project_id: str | None = None
        content_id: str | None = None
        try:
            self.jobs.update(job_id, status="running")
            job = self.jobs.get(job_id)
            assert job is not None
            payload = job["payload"]
            project_id = payload.get("project_id")
            content_id = payload.get("content_id")
            user = db.get(User, UUID(payload["user_id"]))
            content = db.get(Content, UUID(payload["content_id"]))
            if user is None or content is None:
                raise RuntimeError("Content or owner disappeared before publish ran.")
            published = await YouTubeService(db).publish_content(user, content)
            result = {
                "content_id": str(published.id),
                "youtube_video_id": published.youtube_video_id,
                "publish_status": published.publish_status,
            }
            self.jobs.update(
                job_id, status="completed", content_id=str(published.id), result=result
            )
            await notify_job_event(
                event="content.publish.completed",
                job_id=job_id,
                kind="content.publish",
                status="completed",
                project_id=project_id,
                content_id=content_id,
                result=result,
            )
        except Exception as exc:
            detail = getattr(exc, "detail", None)
            message = detail if isinstance(detail, str) else str(detail or exc)
            logger.exception("Automation publish failed job_id=%s", job_id)
            self.jobs.update(job_id, status="failed", error=message)
            await notify_job_event(
                event="content.publish.failed",
                job_id=job_id,
                kind="content.publish",
                status="failed",
                project_id=project_id,
                content_id=content_id,
                error=message,
            )
        finally:
            db.close()

    async def _run_coach(self, job_id: str) -> None:
        db = SessionLocal()
        project_id: str | None = None
        try:
            self.jobs.update(job_id, status="running")
            job = self.jobs.get(job_id)
            assert job is not None
            payload = job["payload"]
            project_id = payload.get("project_id")
            user = db.get(User, UUID(payload["user_id"]))
            if user is None:
                raise RuntimeError("Project owner disappeared before coach ran.")
            result = await AnalyticsService(db).run_coach(
                user, UUID(payload["project_id"]), payload.get("range_days", 30)
            )
            self.jobs.update(job_id, status="completed", result=result)
            # The job itself always completes here (no exception raised);
            # `result["status"]` carries the coach's own semantic outcome
            # (ready / insufficient_data / failed) for n8n to branch on.
            await notify_job_event(
                event=f"analytics.coach.{result.get('status', 'completed')}",
                job_id=job_id,
                kind="analytics.coach",
                status="completed",
                project_id=project_id,
                result=result,
            )
        except Exception as exc:
            detail = getattr(exc, "detail", None)
            message = detail if isinstance(detail, str) else str(detail or exc)
            logger.exception("Automation coach run failed job_id=%s", job_id)
            self.jobs.update(job_id, status="failed", error=message)
            await notify_job_event(
                event="analytics.coach.failed",
                job_id=job_id,
                kind="analytics.coach",
                status="failed",
                project_id=project_id,
                error=message,
            )
        finally:
            db.close()

    @staticmethod
    def public_job(job: dict) -> dict:
        return {
            "job_id": job["job_id"],
            "kind": job["kind"],
            "status": job["status"],
            "content_id": job.get("content_id"),
            "result": job.get("result"),
            "error": job.get("error"),
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
        }
