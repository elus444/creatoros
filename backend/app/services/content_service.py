"""Content/video orchestration (video-first product correction).

Pipeline: Research → Planning → VideoAgent brief → video_generation_service
Primary output is a real video URL when a provider is configured. Never invents
video files. Uses previous content memory and duplicate guards.
"""

from __future__ import annotations

import logging
import secrets
from uuid import UUID

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.agent_run import AgentRun
from app.models.analytics_daily import AnalyticsDaily
from app.models.content import (
    Content,
    ContentFormat,
    ContentStatus,
    GenerationPhase,
    PublishStatus,
)
from app.models.project import Project
from app.models.trend import Trend
from app.models.user import User
from app.schemas.content import (
    ContentExport,
    ContentSuggestRequest,
    ContentSuggestion,
    ContentUpdateRequest,
)
from app.services.agents.base import AgentAttempt, AgentBase, AgentExecutionError
from app.services.agents.kids_shorts_craft import normalize_spoken_narration
from app.services.agents.planning_agent import PlanningAgent
from app.services.agents.research_agent import ResearchAgent
from app.services.agents.suggestion_agent import SuggestionAgent
from app.services.agents.video_agent import VideoAgent
from app.services.job_store import JobStore
from app.services.llm_service import LLMService
from app.services.integration_service import IntegrationService
from app.services.video_generation_service import (
    VideoGenerationError,
    VideoGenerationService,
    VideoProviderNotConfiguredError,
    VideoRateLimitError,
)

logger = logging.getLogger("creatoros.content")

_EDITABLE_STATUSES = {ContentStatus.GENERATED, ContentStatus.REVIEW}
_STATUS_TRANSITIONS = {
    ContentStatus.REVIEW: {ContentStatus.GENERATED},
    ContentStatus.APPROVED: {ContentStatus.REVIEW},
    ContentStatus.EXPORTED: {ContentStatus.APPROVED},
}


class ContentService:
    def __init__(self, db: Session, llm_service: LLMService | None = None):
        self.db = db
        self.llm_service = llm_service or LLMService()
        self.research_agent = ResearchAgent(self.llm_service)
        self.planning_agent = PlanningAgent(self.llm_service)
        self.video_agent = VideoAgent(self.llm_service)
        self.suggestion_agent = SuggestionAgent(self.llm_service)
        self.video_generation = VideoGenerationService()
        self.jobs = JobStore()
        # Back-compat aliases for older tests/imports.
        self.strategy_agent = self.planning_agent
        self.content_agent = self.video_agent

    def _video_provider_for(self, user_id: UUID) -> dict | None:
        return IntegrationService(self.db).resolved_credentials(user_id)

    def get_owned_trend(self, user: User, trend_id: UUID) -> Trend:
        trend = self.db.get(Trend, trend_id)
        if trend is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Trend not found."
            )
        project = self.db.get(Project, trend.project_id)
        if project is None or project.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Trend not found."
            )
        return trend

    def get_owned_content(self, user: User, content_id: UUID) -> Content:
        """Get a content record owned by the user."""
        content = self.db.get(Content, content_id)
        if content is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Content not found."
            )

        project = self.db.get(Project, content.project_id)
        if project is None:
            # Data integrity issue: content exists but its project doesn't.
            # Log it distinctly from a plain 404 so it's easy to spot, but
            # still return a plain 404 to the caller.
            logger.error(
                "Data integrity: content %s references missing project %s",
                content_id,
                content.project_id,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Content not found."
            )

        if project.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Content not found.",  # Don't leak ownership info
            )

        return content

    def get_owned_job(self, user: User, job_id: str) -> dict:
        job = self.jobs.get(job_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Job not found."
            )
        payload = job.get("payload") or {}
        if payload.get("user_id") != str(user.id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Job not found."
            )
        return {
            "job_id": job["job_id"],
            "kind": job.get("kind"),
            "status": job.get("status"),
            "content_id": job.get("content_id") or payload.get("content_id"),
            "error": job.get("error"),
            "result": job.get("result"),
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
        }

    def list_for_user(
        self, user: User, project_id: UUID | None = None
    ) -> list[tuple[Content, Project, Trend]]:
        stmt = (
            select(Content, Project, Trend)
            .join(Project, Content.project_id == Project.id)
            .join(Trend, Content.trend_id == Trend.id)
            .where(Project.user_id == user.id)
            .order_by(Content.created_at.desc())
        )
        if project_id is not None:
            project = self.db.get(Project, project_id)
            if project is None or project.user_id != user.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Project not found."
                )
            stmt = stmt.where(Content.project_id == project_id)

        stmt = stmt.limit(get_settings().max_list_items)
        return list(self.db.execute(stmt).all())

    def to_public(
        self, content: Content, project: Project | None = None, trend: Trend | None = None
    ) -> dict:
        if project is None:
            project = self.db.get(Project, content.project_id)
        if trend is None:
            trend = self.db.get(Trend, content.trend_id)
        video_url = content.video_url
        # Private Supabase objects: mint a short-lived signed URL for the owner.
        if content.storage_key and project is not None:
            try:
                from app.services.storage_service import StorageService

                storage = StorageService()
                settings = get_settings()
                if (settings.storage_backend or "").lower() == "supabase":
                    storage.assert_owner_path(
                        content.storage_key, str(project.user_id)
                    )
                    video_url = storage.create_signed_url(content.storage_key)
            except Exception:
                # Fall back to stored URL rather than breaking the workspace.
                logger.exception(
                    "Failed to sign storage URL for content_id=%s", content.id
                )
        return {
            "id": content.id,
            "project_id": content.project_id,
            "trend_id": content.trend_id,
            "format": content.format,
            "generation_phase": content.generation_phase,
            "research": content.research,
            "strategy": content.strategy,
            "video_plan": content.video_plan,
            "script": content.script,
            "titles": content.titles,
            "captions": content.captions,
            "hashtags": content.hashtags,
            "video_url": video_url,
            "thumbnail_url": content.thumbnail_url,
            "publish_status": content.publish_status,
            "youtube_video_id": content.youtube_video_id,
            "status": content.status,
            "error": content.error,
            "created_at": content.created_at,
            "updated_at": getattr(content, "updated_at", None),
            "project_name": project.name if project else None,
            "trend_title": trend.title if trend else None,
        }

    def enqueue_generate(
        self,
        user: User,
        trend_id: UUID,
        *,
        format: str = ContentFormat.SHORT,
        background_tasks: BackgroundTasks | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        """Non-blocking generate: create PENDING content + Redis job."""
        trend = self.get_owned_trend(user, trend_id)
        if not trend.is_selected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Select this trend before generating content.",
            )
        format = self._validate_format(format)
        project = self.db.get(Project, trend.project_id)
        duplicate = self._find_duplicate(project, trend)
        if duplicate is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": (
                        "A recent video already exists for this trend. "
                        "Open it or choose a different trend."
                    ),
                    "content_id": str(duplicate.id),
                },
            )

        content = Content(
            project_id=project.id,
            trend_id=trend.id,
            format=format,
            status=ContentStatus.PENDING,
            generation_phase=GenerationPhase.QUEUED,
            publish_status=PublishStatus.DRAFT,
        )
        self.db.add(content)
        self.db.commit()
        self.db.refresh(content)

        job = self.jobs.create(
            kind="content.generate",
            payload={
                "content_id": str(content.id),
                "user_id": str(user.id),
                "format": format,
            },
            idempotency_key=idempotency_key,
        )
        if not job.get("idempotent_replay") and background_tasks is not None:
            background_tasks.add_task(self._run_generate_job, job["job_id"])
        return {
            "job_id": job["job_id"],
            "content_id": str(content.id),
            "status": job["status"],
            "generation_phase": content.generation_phase,
        }

    async def generate(
        self, user: User, trend_id: UUID, *, format: str = ContentFormat.SHORT
    ) -> Content:
        """Synchronous generate (tests / automation workers)."""
        trend = self.get_owned_trend(user, trend_id)
        if not trend.is_selected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Select this trend before generating content.",
            )
        format = self._validate_format(format)
        project = self.db.get(Project, trend.project_id)
        duplicate = self._find_duplicate(project, trend)
        if duplicate is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": (
                        "A recent video already exists for this trend. "
                        "Open it or choose a different trend."
                    ),
                    "content_id": str(duplicate.id),
                },
            )

        content = Content(
            project_id=project.id,
            trend_id=trend.id,
            format=format,
            status=ContentStatus.PENDING,
            generation_phase=GenerationPhase.QUEUED,
            publish_status=PublishStatus.DRAFT,
        )
        self.db.add(content)
        self.db.commit()
        self.db.refresh(content)

        try:
            await self._pipeline(content, project, trend)
        except AgentExecutionError as exc:
            self._mark_failed(content, str(exc))
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": f"Video generation pipeline failed: {exc}",
                    "content_id": str(content.id),
                },
            ) from exc
        except VideoProviderNotConfiguredError as exc:
            self._mark_failed(content, str(exc))
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "message": str(exc),
                    "content_id": str(content.id),
                },
            ) from exc
        except VideoRateLimitError as exc:
            self._mark_failed(content, str(exc))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "message": str(exc),
                    "content_id": str(content.id),
                },
            ) from exc
        except VideoGenerationError as exc:
            self._mark_failed(content, str(exc))
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": f"Video provider failed: {exc}",
                    "content_id": str(content.id),
                },
            ) from exc
        except Exception as exc:
            self._mark_failed(content, f"Unexpected error: {exc}")
            logger.exception("Unexpected generate failure content_id=%s", content.id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "message": "Video generation failed unexpectedly.",
                    "content_id": str(content.id),
                },
            ) from exc

        self.db.refresh(content)
        return content

    async def _run_generate_job(self, job_id: str) -> None:
        db = SessionLocal()
        try:
            self.jobs.update(job_id, status="running")
            job = self.jobs.get(job_id)
            assert job is not None
            payload = job["payload"]
            content = db.get(Content, UUID(payload["content_id"]))
            if content is None:
                raise RuntimeError("Content disappeared before job ran.")
            user = db.get(User, UUID(payload["user_id"]))
            project = db.get(Project, content.project_id)
            trend = db.get(Trend, content.trend_id)
            service = ContentService(db)
            await service._pipeline(content, project, trend)
            self.jobs.update(
                job_id,
                status="completed",
                content_id=str(content.id),
                result={"content_id": str(content.id), "status": content.status},
            )
        except Exception as exc:
            logger.exception("Background content.generate failed job_id=%s", job_id)
            detail = getattr(exc, "detail", None)
            if isinstance(detail, dict):
                message = detail.get("message") or str(exc)
            else:
                message = str(detail or exc)
            self.jobs.update(job_id, status="failed", error=message)
            try:
                job = self.jobs.get(job_id)
                if job and job.get("payload", {}).get("content_id"):
                    content = db.get(Content, UUID(job["payload"]["content_id"]))
                    if content is not None:
                        ContentService(db)._mark_failed(content, message)
            except Exception:
                logger.exception("Failed to mark content failed for job_id=%s", job_id)
        finally:
            db.close()

    async def _pipeline(self, content: Content, project: Project, trend: Trend) -> None:
        creator_context = self._creator_context(project)
        memory = self._previous_content_memory(project.id)
        creator_context["previous_content"] = memory
        creator_context["winning_content"] = self._winning_content_memory(project.id)
        creator_context["variety_seed"] = secrets.token_hex(4)
        creator_context["format"] = content.format

        content.generation_phase = GenerationPhase.RESEARCHING
        self.db.commit()
        research_output = await self._run_agent(
            content,
            self.research_agent,
            {
                "trend": self._trend_context(trend),
                **creator_context,
            },
        )
        content.research = research_output
        self.db.commit()

        content.generation_phase = GenerationPhase.PLANNING
        self.db.commit()
        plan_output = await self._run_agent(
            content,
            self.planning_agent,
            {"research": research_output, **creator_context},
        )
        content.strategy = plan_output
        self.db.commit()

        content.generation_phase = GenerationPhase.GENERATING_VIDEO
        self.db.commit()
        video_brief = await self._run_agent(
            content,
            self.video_agent,
            {"strategy": plan_output, **creator_context},
        )
        video_brief = self._finalize_video_brief(video_brief)
        content.video_plan = video_brief
        content.script = video_brief.get("narration")
        content.titles = video_brief.get("titles")
        content.captions = video_brief.get("caption")
        content.hashtags = video_brief.get("hashtags")
        self.db.commit()

        content.generation_phase = GenerationPhase.PROCESSING
        self.db.commit()
        result = await self.video_generation.generate(
            brief=video_brief,
            format=content.format,
            owner_id=str(project.user_id),
            video_provider=self._video_provider_for(project.user_id),
        )
        content.video_url = result.video_url
        content.storage_key = result.storage_key
        content.thumbnail_url = result.thumbnail_url
        content.status = ContentStatus.GENERATED
        content.generation_phase = GenerationPhase.READY
        content.publish_status = PublishStatus.READY
        content.error = None
        self.db.commit()

    def update(
        self, user: User, content_id: UUID, payload: ContentUpdateRequest
    ) -> Content:
        content = self.get_owned_content(user, content_id)
        self._require_editable(content)
        data = payload.model_dump(exclude_unset=True)
        if not data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields provided to update.",
            )
        if "script" in data:
            content.script = data["script"]
        if "titles" in data:
            content.titles = data["titles"]
        if "captions" in data:
            content.captions = data["captions"]
        if "hashtags" in data:
            content.hashtags = [
                tag.lstrip("#").strip() for tag in data["hashtags"] if tag.strip()
            ]
        self.db.commit()
        self.db.refresh(content)
        return content

    def transition_status(self, user: User, content_id: UUID, new_status: str) -> Content:
        content = self.get_owned_content(user, content_id)
        allowed_from = _STATUS_TRANSITIONS.get(new_status, set())
        if content.status not in allowed_from:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot move content from {content.status} to {new_status}. "
                    f"Allowed previous statuses: {sorted(allowed_from) or 'none'}."
                ),
            )
        if new_status == ContentStatus.REVIEW and not content.video_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A generated video file is required before review.",
            )
        content.status = new_status
        content.error = None
        self.db.commit()
        self.db.refresh(content)
        return content

    def export(self, user: User, content_id: UUID) -> ContentExport:
        content = self.transition_status(user, content_id, ContentStatus.EXPORTED)
        project = self.db.get(Project, content.project_id)
        trend = self.db.get(Trend, content.trend_id)
        title = (content.titles or ["untitled"])[0]
        safe_name = "".join(
            ch if ch.isalnum() or ch in "-_" else "-" for ch in title.lower()
        )
        filename = f"{safe_name[:48] or 'video'}.md"
        body = self._render_export_markdown(content, project, trend)
        return ContentExport(
            content_id=content.id,
            status=content.status,
            filename=filename,
            body=body,
        )

    async def regenerate(self, user: User, content_id: UUID) -> Content:
        content = self.get_owned_content(user, content_id)
        if content.status != ContentStatus.FAILED:
            self._require_editable(content)
        if not content.strategy:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Content has no plan to regenerate from.",
            )
        project = self.db.get(Project, content.project_id)
        creator_context = self._creator_context(project)
        creator_context["previous_content"] = self._previous_content_memory(project.id)
        creator_context["winning_content"] = self._winning_content_memory(project.id)
        creator_context["variety_seed"] = secrets.token_hex(4)
        creator_context["format"] = content.format
        try:
            content.generation_phase = GenerationPhase.GENERATING_VIDEO
            self.db.commit()
            video_brief = await self._run_agent(
                content,
                self.video_agent,
                {"strategy": content.strategy, **creator_context},
            )
            video_brief = self._finalize_video_brief(video_brief)
            content.video_plan = video_brief
            content.script = video_brief.get("narration")
            content.titles = video_brief.get("titles")
            content.captions = video_brief.get("caption")
            content.hashtags = video_brief.get("hashtags")
            self.db.commit()
            result = await self.video_generation.generate(
                brief=video_brief,
                format=content.format,
                owner_id=str(project.user_id),
                video_provider=self._video_provider_for(project.user_id),
            )
            content.video_url = result.video_url
            content.storage_key = result.storage_key
            content.thumbnail_url = result.thumbnail_url
            content.status = ContentStatus.GENERATED
            content.generation_phase = GenerationPhase.READY
            content.error = None
            self.db.commit()
        except VideoProviderNotConfiguredError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "message": str(exc),
                    "content_id": str(content.id),
                },
            ) from exc
        except VideoRateLimitError as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "message": str(exc),
                    "content_id": str(content.id),
                },
            ) from exc
        except (AgentExecutionError, VideoGenerationError) as exc:
            logger.warning("Regeneration failed content_id=%s: %s", content.id, exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": f"Video regeneration failed: {exc}",
                    "content_id": str(content.id),
                },
            ) from exc
        self.db.refresh(content)
        return content

    async def suggest(
        self, user: User, content_id: UUID, payload: ContentSuggestRequest
    ) -> ContentSuggestion:
        content = self.get_owned_content(user, content_id)
        self._require_editable(content)
        project = self.db.get(Project, content.project_id)
        current_map = {
            "script": content.script,
            "titles": content.titles,
            "caption": content.captions,
            "hashtags": content.hashtags,
        }
        current = current_map[payload.target]
        if current is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No current {payload.target} value to improve.",
            )
        try:
            output = await self._run_agent(
                content,
                self.suggestion_agent,
                {
                    "target": payload.target,
                    "current": current,
                    "guidance": payload.guidance,
                    "brand_voice": project.brand_voice,
                    "strategy": content.strategy or {},
                },
            )
        except AgentExecutionError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": f"Suggestion generation failed: {exc}",
                    "content_id": str(content.id),
                },
            ) from exc
        return ContentSuggestion(
            target=payload.target,
            suggestions=output["suggestions"],
            rationale=output["rationale"],
        )

    def _require_editable(self, content: Content) -> None:
        if content.status not in _EDITABLE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Content in status {content.status} is locked. "
                    "Only GENERATED or REVIEW packages can be edited."
                ),
            )

    def _finalize_video_brief(self, video_brief: dict) -> dict:
        narration = normalize_spoken_narration(video_brief.get("narration") or "")
        if narration:
            video_brief["narration"] = narration
        return video_brief

    def _content_performance_map(self, project_id: UUID) -> dict:
        rows = self.db.execute(
            select(
                AnalyticsDaily.content_id,
                func.coalesce(func.sum(AnalyticsDaily.views), 0),
                func.coalesce(func.sum(AnalyticsDaily.likes), 0),
                func.coalesce(func.sum(AnalyticsDaily.comments), 0),
            )
            .join(Content, Content.id == AnalyticsDaily.content_id)
            .where(Content.project_id == project_id)
            .group_by(AnalyticsDaily.content_id)
        ).all()
        mapped: dict = {}
        for content_id, views, likes, comments in rows:
            views_i = int(views or 0)
            likes_i = int(likes or 0)
            comments_i = int(comments or 0)
            rate = ((likes_i + comments_i) / views_i * 100) if views_i else 0.0
            mapped[content_id] = {
                "views": views_i,
                "likes": likes_i,
                "comments": comments_i,
                "engagement_rate": round(rate, 4),
            }
        return mapped

    def _winning_content_memory(self, project_id: UUID, limit: int = 3) -> list[dict]:
        ranked = sorted(
            self._content_performance_map(project_id).items(),
            key=lambda item: item[1]["views"],
            reverse=True,
        )
        winners: list[dict] = []
        for content_id, stats in ranked:
            if stats["views"] < 50:
                continue
            content = self.db.get(Content, content_id)
            if content is None:
                continue
            titles = content.titles or []
            plan = content.strategy or {}
            video_plan = content.video_plan or {}
            hooks = plan.get("hooks") or []
            winners.append(
                {
                    "title": titles[0] if titles else None,
                    "angle": plan.get("angle"),
                    "hook": hooks[0] if hooks else None,
                    "concept": video_plan.get("concept"),
                    "views": stats["views"],
                    "engagement_rate": stats["engagement_rate"],
                    "note": "Make a cousin of this, not a copy.",
                }
            )
            if len(winners) >= limit:
                break
        return winners

    def _previous_content_memory(self, project_id: UUID, limit: int = 12) -> list[dict]:
        performance = self._content_performance_map(project_id)
        rows = self.db.scalars(
            select(Content)
            .where(Content.project_id == project_id)
            .order_by(Content.created_at.desc())
            .limit(limit)
        ).all()
        memory = []
        for row in rows:
            titles = row.titles or []
            plan = row.strategy or {}
            video_plan = row.video_plan or {}
            hooks = plan.get("hooks") or []
            stats = performance.get(row.id) or {}
            narration = (row.script or "")[:160]
            memory.append(
                {
                    "content_id": str(row.id),
                    "title": titles[0] if titles else None,
                    "format": row.format,
                    "angle": plan.get("angle"),
                    "hook": hooks[0] if hooks else None,
                    "concept": video_plan.get("concept"),
                    "narration_excerpt": narration or None,
                    "status": row.status,
                    "publish_status": row.publish_status,
                    "youtube_video_id": row.youtube_video_id,
                    "views": stats.get("views", 0),
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
            )
        return memory

    def _find_duplicate(self, project: Project, trend: Trend) -> Content | None:
        """Block a second run only when a real in-progress or finished video exists."""
        return self.db.scalars(
            select(Content)
            .where(
                Content.project_id == project.id,
                Content.trend_id == trend.id,
                or_(
                    Content.status == ContentStatus.PENDING,
                    and_(
                        Content.status.in_(
                            [
                                ContentStatus.GENERATED,
                                ContentStatus.REVIEW,
                                ContentStatus.APPROVED,
                                ContentStatus.EXPORTED,
                            ]
                        ),
                        Content.video_url.is_not(None),
                        Content.video_url != "",
                    ),
                ),
            )
            .order_by(Content.created_at.desc())
            .limit(1)
        ).first()

    @staticmethod
    def _validate_format(value: str) -> str:
        value = (value or ContentFormat.SHORT).strip().lower()
        if value != ContentFormat.SHORT:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="format must be 'short' (YouTube Shorts only).",
            )
        return value

    def _creator_context(self, project: Project) -> dict:
        return {
            "niche": project.niche,
            "audience": project.audience,
            "brand_voice": project.brand_voice,
        }

    def _trend_context(self, trend: Trend) -> dict:
        return {
            "title": trend.title,
            "source": trend.source,
            "url": trend.url,
            "score": trend.score,
            "language": getattr(trend, "language", None),
        }

    def _render_export_markdown(
        self, content: Content, project: Project | None, trend: Trend | None
    ) -> str:
        titles = content.titles or []
        hashtags = " ".join(f"#{tag}" for tag in (content.hashtags or []))
        lines = [
            f"# {titles[0] if titles else 'Untitled video'}",
            "",
            f"- Project: {project.name if project else content.project_id}",
            f"- Trend: {trend.title if trend else content.trend_id}",
            f"- Format: {content.format}",
            f"- Status: {content.status}",
            f"- Publish status: {content.publish_status}",
            f"- Video URL: {content.video_url or 'n/a'}",
            f"- YouTube ID: {content.youtube_video_id or 'n/a'}",
            "",
            "## Titles",
            *[f"- {title}" for title in titles],
            "",
            "## Narration",
            content.script or "",
            "",
            "## Caption",
            content.captions or "",
            "",
            "## Hashtags",
            hashtags,
        ]
        if content.strategy:
            lines.extend(
                [
                    "",
                    "## Plan",
                    f"Angle: {content.strategy.get('angle', '')}",
                    f"Audience: {content.strategy.get('target_audience', '')}",
                ]
            )
        return "\n".join(lines).strip() + "\n"

    def _mark_failed(self, content: Content, error: str) -> None:
        content.status = ContentStatus.FAILED
        content.generation_phase = GenerationPhase.FAILED
        content.error = error
        self.db.commit()
        self.db.refresh(content)

    async def _run_agent(
        self, content: Content, agent: AgentBase, input_data: dict
    ) -> dict:
        try:
            result = await agent.run(input_data)
        except AgentExecutionError as exc:
            for attempt in exc.attempts:
                self._log_attempt(content, agent.name, input_data, attempt)
            raise
        for attempt in result.attempts:
            self._log_attempt(content, agent.name, input_data, attempt)
        return result.output.model_dump()

    def _log_attempt(
        self,
        content: Content,
        agent_name: str,
        input_data: dict,
        attempt: AgentAttempt,
    ) -> None:
        # JSON-safe-ish: UUIDs should already be strings in inputs we build.
        run = AgentRun(
            content_id=content.id,
            project_id=content.project_id,
            agent_name=agent_name,
            attempt=attempt.attempt,
            input=input_data,
            output=attempt.output,
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
        self.db.commit()
