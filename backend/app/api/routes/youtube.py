from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DBSession
from app.services.youtube_service import YouTubeService

router = APIRouter(prefix="/youtube", tags=["youtube"])


class YouTubeStatus(BaseModel):
    connected: bool
    needs_reconnect: bool = False
    channel_id: str | None = None
    channel_title: str | None = None
    channel_thumbnail_url: str | None = None
    oauth_configured: bool
    redirect_uri: str | None = None


class YouTubeAuthUrl(BaseModel):
    authorization_url: str
    state: str


class YouTubeOAuthAppPublic(BaseModel):
    configured: bool
    client_id: str | None = None
    has_secret: bool = False
    from_env: bool = False
    redirect_uri: str


class YouTubeOAuthAppSave(BaseModel):
    client_id: str = Field(min_length=8, max_length=255)
    client_secret: str | None = Field(default=None, max_length=255)


@router.get("/status", response_model=YouTubeStatus)
def youtube_status(current_user: CurrentUser, db: DBSession) -> YouTubeStatus:
    payload = YouTubeService(db).connection_status(current_user)
    return YouTubeStatus.model_validate(payload)


@router.get("/oauth/app", response_model=YouTubeOAuthAppPublic)
def youtube_oauth_app(current_user: CurrentUser, db: DBSession) -> YouTubeOAuthAppPublic:
    return YouTubeOAuthAppPublic.model_validate(
        YouTubeService(db).oauth_app_status(current_user)
    )


@router.put("/oauth/app", response_model=YouTubeOAuthAppPublic)
def youtube_oauth_app_save(
    payload: YouTubeOAuthAppSave, current_user: CurrentUser, db: DBSession
) -> YouTubeOAuthAppPublic:
    saved = YouTubeService(db).save_oauth_app(
        current_user,
        client_id=payload.client_id,
        client_secret=payload.client_secret,
    )
    return YouTubeOAuthAppPublic.model_validate(saved)


@router.delete("/oauth/app", status_code=204)
def youtube_oauth_app_delete(current_user: CurrentUser, db: DBSession) -> None:
    YouTubeService(db).delete_oauth_app(current_user)


@router.get("/oauth/start", response_model=YouTubeAuthUrl)
def youtube_oauth_start(current_user: CurrentUser, db: DBSession) -> YouTubeAuthUrl:
    started = YouTubeService(db).start_authorization(current_user)
    return YouTubeAuthUrl.model_validate(started)


@router.get("/oauth/callback")
def youtube_oauth_callback(
    db: DBSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Google redirect target. Tokens stay on the server; the browser is sent
    back to Settings with a status flag only.
    """
    return YouTubeService(db).complete_oauth(code=code, state=state, error=error)


@router.delete("/connection", status_code=204)
def youtube_disconnect(current_user: CurrentUser, db: DBSession) -> None:
    YouTubeService(db).disconnect(current_user)
