from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status

from app.api.deps import ContentServiceDep, CurrentUser
from app.core.rate_limit import enforce_user_limit
from app.models.content import ContentStatus
from app.schemas.content import (
    ContentExport,
    ContentGenerateAccepted,
    ContentGenerateRequest,
    ContentPublic,
    ContentSuggestRequest,
    ContentSuggestion,
    ContentUpdateRequest,
)
from app.services.youtube_service import YouTubeService

router = APIRouter(prefix="/content", tags=["content"])


def _public(content_service, content) -> ContentPublic:
    return ContentPublic.model_validate(content_service.to_public(content))


def _rate_generate(user: CurrentUser) -> None:
    enforce_user_limit("content.generate", user)


def _rate_suggest(user: CurrentUser) -> None:
    enforce_user_limit("content.suggest", user)


def _rate_regenerate(user: CurrentUser) -> None:
    enforce_user_limit("content.regenerate", user)


@router.get("", response_model=list[ContentPublic])
def list_content(
    current_user: CurrentUser,
    content_service: ContentServiceDep,
    project_id: UUID | None = Query(default=None),
) -> list[ContentPublic]:
    rows = content_service.list_for_user(current_user, project_id=project_id)
    return [
        ContentPublic.model_validate(
            content_service.to_public(content, project=project, trend=trend)
        )
        for content, project, trend in rows
    ]


@router.post(
    "/generate",
    dependencies=[Depends(_rate_generate)],
)
async def generate_content(
    payload: ContentGenerateRequest,
    current_user: CurrentUser,
    content_service: ContentServiceDep,
    background_tasks: BackgroundTasks,
    response: Response,
):
    """Generate a video package.

    async_mode=true (default): enqueue Redis job, return 202 + job/content ids.
    async_mode=false: run pipeline in-request (tests / tooling).
    """
    if payload.async_mode:
        accepted = content_service.enqueue_generate(
            current_user,
            payload.trend_id,
            format=payload.format,
            background_tasks=background_tasks,
        )
        response.status_code = status.HTTP_202_ACCEPTED
        return ContentGenerateAccepted(
            success=True,
            job_id=accepted["job_id"],
            content_id=accepted["content_id"],
            status=accepted["status"],
            generation_phase=accepted.get("generation_phase"),
        )

    content = await content_service.generate(
        current_user, payload.trend_id, format=payload.format
    )
    response.status_code = status.HTTP_201_CREATED
    return _public(content_service, content)


@router.get("/jobs/{job_id}")
def get_generation_job(
    job_id: str,
    current_user: CurrentUser,
    content_service: ContentServiceDep,
):
    """Poll async video-generation job status (owner only)."""
    return content_service.get_owned_job(current_user, job_id)


@router.get("/{content_id}", response_model=ContentPublic)
def get_content(
    content_id: UUID,
    current_user: CurrentUser,
    content_service: ContentServiceDep,
) -> ContentPublic:
    content = content_service.get_owned_content(current_user, content_id)
    return _public(content_service, content)


@router.patch("/{content_id}", response_model=ContentPublic)
def update_content(
    content_id: UUID,
    payload: ContentUpdateRequest,
    current_user: CurrentUser,
    content_service: ContentServiceDep,
) -> ContentPublic:
    content = content_service.update(current_user, content_id, payload)
    return _public(content_service, content)


@router.post("/{content_id}/review", response_model=ContentPublic)
def mark_review(
    content_id: UUID,
    current_user: CurrentUser,
    content_service: ContentServiceDep,
) -> ContentPublic:
    content = content_service.transition_status(
        current_user, content_id, ContentStatus.REVIEW
    )
    return _public(content_service, content)


@router.post("/{content_id}/approve", response_model=ContentPublic)
def approve_content(
    content_id: UUID,
    current_user: CurrentUser,
    content_service: ContentServiceDep,
) -> ContentPublic:
    content = content_service.transition_status(
        current_user, content_id, ContentStatus.APPROVED
    )
    return _public(content_service, content)


@router.post("/{content_id}/export", response_model=ContentExport)
def export_content(
    content_id: UUID,
    current_user: CurrentUser,
    content_service: ContentServiceDep,
) -> ContentExport:
    return content_service.export(current_user, content_id)


@router.post("/{content_id}/publish", response_model=ContentPublic)
async def publish_to_youtube(
    content_id: UUID,
    current_user: CurrentUser,
    content_service: ContentServiceDep,
) -> ContentPublic:
    content = content_service.get_owned_content(current_user, content_id)
    youtube = YouTubeService(content_service.db)
    published = await youtube.publish_content(current_user, content)
    return _public(content_service, published)


@router.post(
    "/{content_id}/regenerate",
    response_model=ContentPublic,
    dependencies=[Depends(_rate_regenerate)],
)
async def regenerate_content(
    content_id: UUID,
    current_user: CurrentUser,
    content_service: ContentServiceDep,
) -> ContentPublic:
    content = await content_service.regenerate(current_user, content_id)
    return _public(content_service, content)


@router.post(
    "/{content_id}/suggest",
    response_model=ContentSuggestion,
    dependencies=[Depends(_rate_suggest)],
)
async def suggest_content(
    content_id: UUID,
    payload: ContentSuggestRequest,
    current_user: CurrentUser,
    content_service: ContentServiceDep,
) -> ContentSuggestion:
    return await content_service.suggest(current_user, content_id, payload)
