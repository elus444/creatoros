from fastapi import APIRouter

from app.api.deps import CurrentUser, DBSession
from app.core.rate_limit import enforce_user_limit
from app.schemas.integrations import (
    VideoProviderPublic,
    VideoProviderSave,
    VideoProviderTestRequest,
    VideoProviderTestResult,
)
from app.services.integration_service import IntegrationService

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/video", response_model=VideoProviderPublic)
def video_provider_status(
    current_user: CurrentUser, db: DBSession
) -> VideoProviderPublic:
    return VideoProviderPublic.model_validate(
        IntegrationService(db).public_status(current_user)
    )


@router.put("/video", response_model=VideoProviderPublic)
def video_provider_save(
    payload: VideoProviderSave, current_user: CurrentUser, db: DBSession
) -> VideoProviderPublic:
    saved = IntegrationService(db).save(
        current_user,
        provider=payload.provider,
        model_id=payload.model_id,
        api_key=payload.api_key,
    )
    return VideoProviderPublic.model_validate(saved)


@router.delete("/video", status_code=204)
def video_provider_delete(current_user: CurrentUser, db: DBSession) -> None:
    IntegrationService(db).delete(current_user)


@router.post("/video/test", response_model=VideoProviderTestResult)
async def video_provider_test(
    payload: VideoProviderTestRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> VideoProviderTestResult:
    enforce_user_limit("integrations-test", current_user)
    result = await IntegrationService(db).test_connection(
        current_user,
        provider=payload.provider,
        api_key=payload.api_key,
    )
    return VideoProviderTestResult.model_validate(result)
