import logging
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent_run import AgentRun
from app.models.content import Content, ContentStatus
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
from app.services.agents.content_agent import ContentAgent
from app.services.agents.research_agent import ResearchAgent
from app.services.agents.strategy_agent import StrategyAgent
from app.services.agents.suggestion_agent import SuggestionAgent
from app.services.llm_service import LLMService

logger = logging.getLogger("creatoros.content")

_EDITABLE_STATUSES = {ContentStatus.GENERATED, ContentStatus.REVIEW}
_STATUS_TRANSITIONS = {
    ContentStatus.REVIEW: {ContentStatus.GENERATED},
    ContentStatus.APPROVED: {ContentStatus.REVIEW},
    ContentStatus.EXPORTED: {ContentStatus.APPROVED},
}


class ContentService:
    """Orchestrates the Research -> Strategy -> Content agent pipeline
    (Constitution §7) and owns the M4 Content Workspace mutations:
    edit, suggest, regenerate, review, approve, export.
    """

    def __init__(self, db: Session, llm_service: LLMService | None = None):
        self.db = db
        self.llm_service = llm_service or LLMService()
        self.research_agent = ResearchAgent(self.llm_service)
        self.strategy_agent = StrategyAgent(self.llm_service)
        self.content_agent = ContentAgent(self.llm_service)
        self.suggestion_agent = SuggestionAgent(self.llm_service)

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
        return list(self.db.execute(stmt).all())

    def to_public(
        self, content: Content, project: Project | None = None, trend: Trend | None = None
    ) -> dict:
        if project is None:
            project = self.db.get(Project, content.project_id)
        if trend is None:
            trend = self.db.get(Trend, content.trend_id)
        return {
            "id": content.id,
            "project_id": content.project_id,
            "trend_id": content.trend_id,
            "research": content.research,
            "strategy": content.strategy,
            "script": content.script,
            "titles": content.titles,
            "captions": content.captions,
            "hashtags": content.hashtags,
            "status": content.status,
            "error": content.error,
            "created_at": content.created_at,
            "project_name": project.name if project else None,
            "trend_title": trend.title if trend else None,
        }

    async def generate(self, user: User, trend_id: UUID) -> Content:
        trend = self.get_owned_trend(user, trend_id)
        if not trend.is_selected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Select this trend before generating content.",
            )
        project = self.db.get(Project, trend.project_id)

        content = Content(
            project_id=project.id,
            trend_id=trend.id,
            status=ContentStatus.PENDING,
        )
        self.db.add(content)
        self.db.commit()
        self.db.refresh(content)

        creator_context = self._creator_context(project)
        trend_context = self._trend_context(trend)

        try:
            research_output = await self._run_agent(
                content,
                self.research_agent,
                {"trend": trend_context, **creator_context},
            )
            content.research = research_output
            self.db.commit()

            strategy_output = await self._run_agent(
                content,
                self.strategy_agent,
                {"research": research_output, **creator_context},
            )
            content.strategy = strategy_output
            self.db.commit()

            await self._apply_content_agent(content, strategy_output, creator_context)
            content.status = ContentStatus.GENERATED
            content.error = None
            self.db.commit()
        except AgentExecutionError as exc:
            self._mark_failed(content, str(exc))
            logger.warning(
                "Content generation failed for content_id=%s: %s", content.id, exc
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": f"Content generation failed: {exc}",
                    "content_id": str(content.id),
                },
            ) from exc
        except Exception as exc:
            self._mark_failed(content, f"Unexpected error: {exc}")
            logger.exception(
                "Unexpected content generation failure for content_id=%s", content.id
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "message": "Content generation failed unexpectedly.",
                    "content_id": str(content.id),
                },
            ) from exc

        self.db.refresh(content)
        return content

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
            # Strip leading # so storage stays consistent with the Content Agent.
            content.hashtags = [tag.lstrip("#").strip() for tag in data["hashtags"] if tag.strip()]
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
        if new_status == ContentStatus.REVIEW and not content.script:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Content needs a script before it can enter review.",
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
        safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in title.lower())
        filename = f"{safe_name[:48] or 'content'}.md"
        body = self._render_export_markdown(content, project, trend)
        return ContentExport(
            content_id=content.id,
            status=content.status,
            filename=filename,
            body=body,
        )

    async def regenerate(self, user: User, content_id: UUID) -> Content:
        """Re-runs the Content Agent using the existing strategy (research/
        strategy stay intact). Allowed only while the package is still
        editable (GENERATED / REVIEW).
        """
        content = self.get_owned_content(user, content_id)
        self._require_editable(content)
        if not content.strategy:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Content has no strategy to regenerate from.",
            )
        project = self.db.get(Project, content.project_id)
        creator_context = self._creator_context(project)

        try:
            await self._apply_content_agent(content, content.strategy, creator_context)
            content.status = ContentStatus.GENERATED
            content.error = None
            self.db.commit()
        except AgentExecutionError as exc:
            # Keep previous draft intact — regeneration failure is not a
            # content-package failure (Constitution §22: don't destroy good data).
            logger.warning(
                "Content regeneration failed for content_id=%s: %s", content.id, exc
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": f"Content regeneration failed: {exc}",
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

    async def _apply_content_agent(
        self, content: Content, strategy: dict, creator_context: dict
    ) -> None:
        content_output = await self._run_agent(
            content,
            self.content_agent,
            {"strategy": strategy, **creator_context},
        )
        content.script = content_output["script"]
        content.titles = content_output["titles"]
        content.captions = content_output["caption"]
        content.hashtags = content_output["hashtags"]

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
        }

    def _render_export_markdown(
        self, content: Content, project: Project | None, trend: Trend | None
    ) -> str:
        titles = content.titles or []
        hashtags = " ".join(f"#{tag}" for tag in (content.hashtags or []))
        lines = [
            f"# {titles[0] if titles else 'Untitled content'}",
            "",
            f"- Project: {project.name if project else content.project_id}",
            f"- Trend: {trend.title if trend else content.trend_id}",
            f"- Status: {content.status}",
            "",
            "## Titles",
            *[f"- {title}" for title in titles],
            "",
            "## Script",
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
                    "## Strategy",
                    f"Angle: {content.strategy.get('angle', '')}",
                    f"Audience: {content.strategy.get('target_audience', '')}",
                ]
            )
        return "\n".join(lines).strip() + "\n"

    def _mark_failed(self, content: Content, error: str) -> None:
        content.status = ContentStatus.FAILED
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
        run = AgentRun(
            content_id=content.id,
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
