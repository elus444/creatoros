from uuid import UUID

from fastapi import APIRouter

from app.api.deps import OwnedProject, TrendServiceDep
from app.schemas.trend import TrendCollectRequest, TrendCollectResponse, TrendPublic

router = APIRouter(prefix="/projects/{project_id}/trends", tags=["trends"])


@router.get("", response_model=list[TrendPublic])
def list_trends(
    project: OwnedProject,
    trend_service: TrendServiceDep,
) -> list[TrendPublic]:
    trends = trend_service.list_for_project(project)
    return [TrendPublic.model_validate(trend) for trend in trends]


@router.post("/collect", response_model=TrendCollectResponse)
async def collect_trends(
    project: OwnedProject,
    trend_service: TrendServiceDep,
    payload: TrendCollectRequest | None = None,
) -> TrendCollectResponse:
    query = payload.query if payload else None
    trends, collected, sources_used, warnings = await trend_service.collect(project, query)
    return TrendCollectResponse(
        trends=[TrendPublic.model_validate(trend) for trend in trends],
        collected=collected,
        sources_used=sources_used,
        warnings=warnings,
    )


@router.post("/{trend_id}/select", response_model=TrendPublic)
def select_trend(
    trend_id: UUID,
    project: OwnedProject,
    trend_service: TrendServiceDep,
) -> TrendPublic:
    trend = trend_service.select_trend(project, trend_id)
    return TrendPublic.model_validate(trend)
