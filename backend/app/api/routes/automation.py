import hmac
import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status

from app.api.deps import AutomationServiceDep, CurrentUser
from app.core.config import get_settings
from app.core.rate_limit import enforce_request_limit
from app.schemas.analytics import AnalyticsDailyPublic, AnalyticsIngestRequest
from app.schemas.automation import (
    AutomationContentGenerateRequest,
    AutomationCoachRequest,
    AutomationJobAccepted,
    AutomationJobPublic,
    AutomationStatusPublic,
    AutomationTrendCollectRequest,
)

logger = logging.getLogger("creatoros.automation")

router = APIRouter(prefix="/automation", tags=["automation"])


def require_automation_secret(
    x_automation_secret: str | None = Header(default=None, alias="X-Automation-Secret"),
) -> None:
    """Shared-secret gate for n8n -> FastAPI calls.

    Compares secrets with hmac.compare_digest. Never logs the secret value.
    """
    expected = get_settings().n8n_webhook_secret
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Automation is not configured (N8N_WEBHOOK_SECRET is unset).",
        )
    if not x_automation_secret or not hmac.compare_digest(
        x_automation_secret, expected
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid automation credentials.",
        )


def _rate_automation(request: Request) -> None:
    enforce_request_limit("automation", request)

@router.post(
    "/trends/collect",
    response_model=AutomationJobAccepted,
    dependencies=[Depends(require_automation_secret), Depends(_rate_automation)],
)
async def automation_collect_trends(
    payload: AutomationTrendCollectRequest,
    automation_service: AutomationServiceDep,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> AutomationJobAccepted:
    """Trigger existing TrendService.collect for a project (async job)."""
    job = automation_service.enqueue_trend_collect(
        project_id=payload.project_id,
        query=payload.query,
        idempotency_key=_scoped_idempotency(
            "trends.collect", payload.project_id, idempotency_key
        ),
        background_tasks=background_tasks,
    )
    return AutomationJobAccepted(
        success=True,
        job_id=job["job_id"],
        status=job["status"] if job["status"] != "queued" else "queued",
        idempotent_replay=bool(job.get("idempotent_replay")),
    )


@router.post(
    "/content/generate",
    response_model=AutomationJobAccepted,
    dependencies=[Depends(require_automation_secret), Depends(_rate_automation)],
)
async def automation_generate_content(
    payload: AutomationContentGenerateRequest,
    automation_service: AutomationServiceDep,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> AutomationJobAccepted:
    """Enqueue existing ContentService.generate (Research→Strategy→Content)."""
    job = automation_service.enqueue_content_generate(
        project_id=payload.project_id,
        trend_id=payload.trend_id,
        idempotency_key=_scoped_idempotency(
            "content.generate",
            f"{payload.project_id}:{payload.trend_id or 'top'}",
            idempotency_key,
        ),
        background_tasks=background_tasks,
    )
    return AutomationJobAccepted(
        success=True,
        job_id=job["job_id"],
        status=job["status"] if job["status"] != "queued" else "queued",
        idempotent_replay=bool(job.get("idempotent_replay")),
    )


@router.post(
    "/content/{content_id}/publish",
    response_model=AutomationJobAccepted,
    dependencies=[Depends(require_automation_secret), Depends(_rate_automation)],
)
async def automation_publish_content(
    content_id: UUID,
    automation_service: AutomationServiceDep,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> AutomationJobAccepted:
    """Publish approved content to YouTube (async job).

    Uploading is a slow, external HTTP call — this returns immediately
    with a job_id; poll GET /automation/jobs/{job_id} or configure
    N8N_NOTIFY_WEBHOOK_URL for a completion callback. Idempotency-Key
    protects against a retried webhook triggering a second upload; the
    underlying YouTubeService.publish_content also atomically refuses to
    start a second upload for content already uploading/published.
    """
    job = automation_service.enqueue_publish(
        content_id=content_id,
        idempotency_key=_scoped_idempotency(
            "content.publish", content_id, idempotency_key
        ),
        background_tasks=background_tasks,
    )
    return AutomationJobAccepted(
        success=True,
        job_id=job["job_id"],
        status=job["status"] if job["status"] != "queued" else "queued",
        idempotent_replay=bool(job.get("idempotent_replay")),
    )


@router.post(
    "/projects/{project_id}/coach",
    response_model=AutomationJobAccepted,
    dependencies=[Depends(require_automation_secret), Depends(_rate_automation)],
)
async def automation_run_coach(
    project_id: UUID,
    automation_service: AutomationServiceDep,
    background_tasks: BackgroundTasks,
    payload: AutomationCoachRequest | None = None,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> AutomationJobAccepted:
    """Run the weekly analytics/coach agent for a project (async job).

    Calls LLM agents, so it is queued the same way as content generation
    rather than run inline. Returns `status: insufficient_data` in the
    job result (not an error) if the project doesn't have enough
    published content with metrics yet.
    """
    range_days = payload.range_days if payload else 30
    job = automation_service.enqueue_coach(
        project_id=project_id,
        range_days=range_days,
        idempotency_key=_scoped_idempotency(
            "analytics.coach", f"{project_id}:{range_days}", idempotency_key
        ),
        background_tasks=background_tasks,
    )
    return AutomationJobAccepted(
        success=True,
        job_id=job["job_id"],
        status=job["status"] if job["status"] != "queued" else "queued",
        idempotent_replay=bool(job.get("idempotent_replay")),
    )


@router.post(
    "/analytics/ingest",
    response_model=AnalyticsDailyPublic,
    dependencies=[Depends(require_automation_secret), Depends(_rate_automation)],
)
def automation_ingest_analytics(
    payload: AnalyticsIngestRequest,
    automation_service: AutomationServiceDep,
) -> AnalyticsDailyPublic:
    """Upsert a daily metrics snapshot for content (synchronous).

    A single-row upsert is fast enough to answer inline rather than as a
    background job — n8n gets the stored row back in the same response.
    Re-sending the same (content_id, date) overwrites rather than
    duplicates, so a retried webhook call is naturally idempotent.
    """
    row = automation_service.ingest_analytics(payload)
    return AnalyticsDailyPublic.model_validate(row)


@router.get(
    "/jobs/{job_id}",
    response_model=AutomationJobPublic,
    dependencies=[Depends(require_automation_secret)],
)
def automation_job_status(
    job_id: str,
    automation_service: AutomationServiceDep,
) -> AutomationJobPublic:
    job = automation_service.get_job(job_id)
    return AutomationJobPublic.model_validate(automation_service.public_job(job))


@router.get("/status", response_model=AutomationStatusPublic)
def automation_ui_status(
    current_user: CurrentUser,
    automation_service: AutomationServiceDep,
) -> AutomationStatusPublic:
    """JWT-protected snapshot for the in-app Automation page."""
    settings = get_settings()
    if not settings.n8n_webhook_secret:
        return AutomationStatusPublic(automation_configured=False, recent_jobs=[])
    return AutomationStatusPublic.model_validate(
        automation_service.status_snapshot(current_user)
    )


def _scoped_idempotency(kind: str, scope: object, raw_key: str | None) -> str | None:
    if not raw_key:
        return None
    return f"{kind}:{scope}:{raw_key.strip()}"
