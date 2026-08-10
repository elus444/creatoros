from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import ContentServiceDep, CurrentUser
from app.models.content import ContentStatus
from app.schemas.content import (
    ContentExport,
    ContentGenerateRequest,
    ContentPublic,
    ContentSuggestRequest,
    ContentSuggestion,
    ContentUpdateRequest,
)

router = APIRouter(prefix="/content", tags=["content"])


def _public(content_service, content) -> ContentPublic:
    return ContentPublic.model_validate(content_service.to_public(content))


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
    "/generate", response_model=ContentPublic, status_code=status.HTTP_201_CREATED
)
async def generate_content(
    payload: ContentGenerateRequest,
    current_user: CurrentUser,
    content_service: ContentServiceDep,
) -> ContentPublic:
    content = await content_service.generate(current_user, payload.trend_id)
    return _public(content_service, content)


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


@router.post("/{content_id}/regenerate", response_model=ContentPublic)
async def regenerate_content(
    content_id: UUID,
    current_user: CurrentUser,
    content_service: ContentServiceDep,
) -> ContentPublic:
    content = await content_service.regenerate(current_user, content_id)
    return _public(content_service, content)


@router.post("/{content_id}/suggest", response_model=ContentSuggestion)
async def suggest_content(
    content_id: UUID,
    payload: ContentSuggestRequest,
    current_user: CurrentUser,
    content_service: ContentServiceDep,
) -> ContentSuggestion:
    return await content_service.suggest(current_user, content_id, payload)
