from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import AnalyticsServiceDep, CurrentUser
from app.core.rate_limit import enforce_user_limit
from app.schemas.analytics import (
    AnalyticsDailyPublic,
    AnalyticsIngestRequest,
    AnalyticsSyncResult,
    ContentAnalyticsSummary,
    CoachResponse,
    ProjectAnalyticsSummary,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _rate_ingest(user: CurrentUser) -> None:
    enforce_user_limit("analytics.ingest", user)


def _rate_coach(user: CurrentUser) -> None:
    enforce_user_limit("analytics.coach", user)


@router.post(
    "/ingest",
    response_model=AnalyticsDailyPublic,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_rate_ingest)],
)
def ingest_analytics(
    payload: AnalyticsIngestRequest,
    current_user: CurrentUser,
    analytics_service: AnalyticsServiceDep,
) -> AnalyticsDailyPublic:
    """Store (or upsert) a daily performance snapshot for owned content."""
    row = analytics_service.ingest(current_user, payload)
    return AnalyticsDailyPublic(
        id=row.id,
        content_id=row.content_id,
        views=row.views,
        likes=row.likes,
        comments=row.comments,
        engagement_rate=float(row.engagement_rate),
        date=row.date,
        created_at=row.created_at,
    )


@router.post(
    "/projects/{project_id}/sync",
    response_model=AnalyticsSyncResult,
    dependencies=[Depends(_rate_ingest)],
)
def sync_project_analytics(
    project_id: UUID,
    current_user: CurrentUser,
    analytics_service: AnalyticsServiceDep,
) -> AnalyticsSyncResult:
    """Refresh stored daily metrics from live YouTube video statistics."""
    data = analytics_service.sync_from_youtube(
        current_user, project_id, force=True
    )
    return AnalyticsSyncResult.model_validate(data)


@router.get(
    "/projects/{project_id}",
    response_model=ProjectAnalyticsSummary,
)
def project_analytics(
    project_id: UUID,
    current_user: CurrentUser,
    analytics_service: AnalyticsServiceDep,
    range_days: int = Query(default=30, description="7, 30, or 90"),
) -> ProjectAnalyticsSummary:
    data = analytics_service.project_summary(
        current_user, project_id, range_days=range_days
    )
    return ProjectAnalyticsSummary.model_validate(data)


@router.get(
    "/content/{content_id}",
    response_model=ContentAnalyticsSummary,
)
def content_analytics(
    content_id: UUID,
    current_user: CurrentUser,
    analytics_service: AnalyticsServiceDep,
    range_days: int = Query(default=90, description="7, 30, or 90"),
) -> ContentAnalyticsSummary:
    data = analytics_service.content_summary(
        current_user, content_id, range_days=range_days
    )
    return ContentAnalyticsSummary.model_validate(data)


@router.post(
    "/projects/{project_id}/coach",
    response_model=CoachResponse,
    dependencies=[Depends(_rate_coach)],
)
async def project_coach(
    project_id: UUID,
    current_user: CurrentUser,
    analytics_service: AnalyticsServiceDep,
    range_days: int = Query(default=30, description="7, 30, or 90"),
) -> CoachResponse:
    """Run Analytics Agent → Coach Agent on stored project metrics."""
    data = await analytics_service.run_coach(
        current_user, project_id, range_days=range_days
    )
    return CoachResponse.model_validate(data)
