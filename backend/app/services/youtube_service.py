"""YouTube OAuth connection and Shorts publishing (YouTube-only).

Tokens and OAuth secrets stay encrypted server-side and are never returned
to the frontend. Without a connected channel, publish fails clearly — it
does not fake an upload. n8n can still trigger the same FastAPI publish
path later; the in-app Publish button uses this service directly.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, urlencode, urljoin
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import redis as redis_module
from app.core.config import get_settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.models.content import Content, ContentStatus, PublishStatus
from app.models.user import User
from app.models.youtube_credential import YouTubeCredential
from app.models.youtube_oauth_app import YouTubeOAuthApp
from app.services.storage_service import StorageError, StorageService

logger = logging.getLogger("creatoros.youtube")

# Upload permission only — include_granted_scopes is a separate OAuth param.
YOUTUBE_SCOPES = "https://www.googleapis.com/auth/youtube.upload"
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
_YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
_YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
_YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
_HTTP_TIMEOUT = 15.0
_UPLOAD_TIMEOUT = httpx.Timeout(connect=30.0, read=300.0, write=300.0, pool=30.0)
_EXPIRY_SKEW = timedelta(seconds=60)
_PUBLISHABLE_STATUSES = {ContentStatus.APPROVED, ContentStatus.EXPORTED}


class YouTubeNotConfiguredError(Exception):
    pass


def _clean_oauth_value(value: str | None) -> str:
    cleaned = (value or "").replace("\ufeff", "").replace("\u200b", "").strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _thumbnail_url(snippet: dict) -> str | None:
    thumbs = snippet.get("thumbnails") or {}
    for key in ("high", "medium", "default"):
        url = (thumbs.get(key) or {}).get("url")
        if isinstance(url, str) and url.strip():
            return url.strip()[:500]
    return None


def _int_stat(value) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return 0
    return max(number, 0)


class YouTubeService:
    def __init__(self, db: Session):
        self.db = db

    def _redirect_uri(self) -> str:
        return (
            get_settings().youtube_oauth_redirect_uri
            or "http://localhost:8000/api/v1/youtube/oauth/callback"
        )

    def _oauth_app_row(self, user_id: UUID) -> YouTubeOAuthApp | None:
        return self.db.scalars(
            select(YouTubeOAuthApp).where(YouTubeOAuthApp.user_id == user_id)
        ).first()

    def _settings_oauth_pair(self, user: User) -> tuple[str, str] | None:
        """Return the Settings-saved (client_id, secret) only if it can be decrypted."""
        row = self._oauth_app_row(user.id)
        if row is None:
            return None
        try:
            secret = decrypt_secret(row.client_secret_encrypted, get_settings().jwt_secret)
        except ValueError:
            logger.warning("Stored Google client secret could not be decrypted for user %s", user.id)
            return None
        client_id = _clean_oauth_value(row.client_id)
        secret = _clean_oauth_value(secret)
        if client_id and secret:
            return client_id, secret
        return None

    def _oauth_client_for(self, user: User) -> tuple[str, str, str] | None:
        """Return (client_id, client_secret, redirect_uri). Env secrets win.

        Google client ID/secret are backend environment secrets, not frontend
        settings. A previously saved Settings row is only a fallback.
        """
        redirect_uri = self._redirect_uri()
        settings = get_settings()
        env_id = _clean_oauth_value(settings.youtube_oauth_client_id)
        env_secret = _clean_oauth_value(settings.youtube_oauth_client_secret)
        if env_id and env_secret:
            return env_id, env_secret, redirect_uri
        saved = self._settings_oauth_pair(user)
        if saved is not None:
            return saved[0], saved[1], redirect_uri
        return None

    def oauth_app_status(self, user: User) -> dict:
        saved = self._settings_oauth_pair(user)
        env_ok = bool(
            _clean_oauth_value(get_settings().youtube_oauth_client_id)
            and _clean_oauth_value(get_settings().youtube_oauth_client_secret)
        )
        return {
            "configured": self._oauth_client_for(user) is not None,
            "client_id": None if env_ok else (saved[0] if saved else None),
            "has_secret": env_ok or saved is not None,
            "from_env": env_ok,
            "redirect_uri": self._redirect_uri(),
        }

    def save_oauth_app(self, user: User, *, client_id: str, client_secret: str | None) -> dict:
        client_id = _clean_oauth_value(client_id)
        secret_in = _clean_oauth_value(client_secret)
        if not client_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google OAuth client ID is required.",
            )
        row = self._oauth_app_row(user.id)
        if row is not None and client_id != _clean_oauth_value(row.client_id) and not secret_in:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A new Google client ID needs its matching client secret.",
            )
        if not secret_in and row is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google OAuth client secret is required.",
            )
        vault = get_settings().jwt_secret
        if secret_in:
            encrypted = encrypt_secret(secret_in, vault)
            if decrypt_secret(encrypted, vault) != secret_in:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Could not store the Google client secret securely. Try again.",
                )
        else:
            encrypted = None
        if row is None:
            if not encrypted:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Google OAuth client secret is required.",
                )
            row = YouTubeOAuthApp(
                user_id=user.id,
                client_id=client_id,
                client_secret_encrypted=encrypted,
            )
            self.db.add(row)
        else:
            row.client_id = client_id
            if encrypted:
                row.client_secret_encrypted = encrypted
        self.db.commit()
        status_payload = self.oauth_app_status(user)
        if not status_payload["configured"] or not status_payload["has_secret"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Google client was saved but could not be read back. Try removing it and saving again.",
            )
        return status_payload

    def delete_oauth_app(self, user: User) -> None:
        row = self._oauth_app_row(user.id)
        if row is None:
            return
        self.db.delete(row)
        self.db.commit()

    def _require_oauth_config(self, user: User | None = None) -> tuple[str, str, str]:
        if user is not None:
            resolved = self._oauth_client_for(user)
            if resolved:
                return resolved
        if user is None:
            settings = get_settings()
            if (
                settings.youtube_oauth_client_id
                and settings.youtube_oauth_client_secret
            ):
                return (
                    settings.youtube_oauth_client_id,
                    settings.youtube_oauth_client_secret,
                    self._redirect_uri(),
                )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "YouTube OAuth is not configured. Set YOUTUBE_OAUTH_CLIENT_ID and "
                "YOUTUBE_OAUTH_CLIENT_SECRET on the backend, then try Connect YouTube again."
            ),
        )

    def _credential_for(self, user_id: UUID) -> YouTubeCredential | None:
        return self.db.scalars(
            select(YouTubeCredential).where(YouTubeCredential.user_id == user_id)
        ).first()

    def _frontend_redirect(self, query: str) -> RedirectResponse:
        base = get_settings().frontend_url.rstrip("/") + "/"
        target = urljoin(base, f"settings?{query}")
        return RedirectResponse(url=target, status_code=302)

    def start_authorization(self, user: User) -> dict:
        client_id, _client_secret, redirect_uri = self._require_oauth_config(user)
        state = secrets.token_urlsafe(32)
        redis_module.store_oauth_state(state, str(user.id))
        params = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": YOUTUBE_SCOPES,
                "access_type": "offline",
                "prompt": "consent",
                "include_granted_scopes": "true",
                "state": state,
            },
            quote_via=quote,
            safe=":/",
        )
        return {
            "authorization_url": f"{_GOOGLE_AUTH_URL}?{params}",
            "state": state,
        }

    def authorization_url(self, user: User, state: str) -> str:
        """Back-compat helper used by older callers/tests."""
        started = self.start_authorization(user)
        return started["authorization_url"]

    def connection_status(self, user: User) -> dict:
        row = self._credential_for(user.id)
        needs_reconnect = False
        if row is not None:
            try:
                self._ensure_fresh_access_token(row)
            except HTTPException:
                needs_reconnect = True
            except Exception:
                logger.exception("YouTube token refresh failed for user %s", user.id)
                needs_reconnect = True
        return {
            "connected": row is not None and not needs_reconnect,
            "needs_reconnect": needs_reconnect,
            "channel_id": row.channel_id if row else None,
            "channel_title": row.channel_title if row else None,
            "channel_thumbnail_url": row.channel_thumbnail_url if row else None,
            "oauth_configured": self._oauth_client_for(user) is not None,
            "redirect_uri": self._redirect_uri(),
        }

    def store_tokens_for_tests(
        self,
        user: User,
        *,
        access_token: str,
        refresh_token: str | None = None,
        channel_id: str | None = None,
        channel_title: str | None = None,
        channel_thumbnail_url: str | None = None,
    ) -> YouTubeCredential:
        """Test/helper path — not a public API."""
        secret = get_settings().jwt_secret
        row = self._upsert_credential(
            user_id=user.id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=3600,
            channel_id=channel_id,
            channel_title=channel_title,
            channel_thumbnail_url=channel_thumbnail_url,
            secret=secret,
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def _upsert_credential(
        self,
        *,
        user_id: UUID,
        access_token: str,
        refresh_token: str | None,
        expires_in: int | None,
        channel_id: str | None,
        channel_title: str | None,
        channel_thumbnail_url: str | None,
        secret: str,
    ) -> YouTubeCredential:
        row = self._credential_for(user_id)
        expiry = datetime.now(tz=UTC) + timedelta(seconds=max(int(expires_in or 3600), 60))
        if row is None:
            row = YouTubeCredential(
                user_id=user_id,
                access_token_encrypted=encrypt_secret(access_token, secret),
                refresh_token_encrypted=(
                    encrypt_secret(refresh_token, secret) if refresh_token else None
                ),
                channel_id=channel_id,
                channel_title=channel_title,
                channel_thumbnail_url=channel_thumbnail_url,
                scopes=YOUTUBE_SCOPES,
                token_expiry=expiry,
            )
            self.db.add(row)
            return row
        row.access_token_encrypted = encrypt_secret(access_token, secret)
        if refresh_token:
            row.refresh_token_encrypted = encrypt_secret(refresh_token, secret)
        row.channel_id = channel_id or row.channel_id
        row.channel_title = channel_title or row.channel_title
        row.channel_thumbnail_url = channel_thumbnail_url or row.channel_thumbnail_url
        row.scopes = YOUTUBE_SCOPES
        row.token_expiry = expiry
        return row

    def _google_token_request(self, data: dict) -> dict:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            response = client.post(_GOOGLE_TOKEN_URL, data=data)
        if response.status_code >= 400:
            google_error = None
            try:
                body = response.json()
                if isinstance(body, dict):
                    google_error = body.get("error")
            except ValueError:
                google_error = None
            logger.warning(
                "Google token endpoint returned HTTP %s error=%s",
                response.status_code,
                google_error or "unknown",
            )
            if google_error == "invalid_client":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="invalid_client",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google could not issue YouTube tokens. Try connecting again.",
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Google returned an unreadable token response.",
            ) from exc
        if not isinstance(payload, dict) or not payload.get("access_token"):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Google did not return an access token.",
            )
        return payload

    def _fetch_channel(self, access_token: str) -> tuple[str | None, str | None, str | None]:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            response = client.get(
                _YOUTUBE_CHANNELS_URL,
                params={"part": "snippet", "mine": "true"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if response.status_code >= 400:
            logger.warning("YouTube channels.list returned HTTP %s", response.status_code)
            return None, None, None
        try:
            payload = response.json()
        except ValueError:
            return None, None, None
        items = payload.get("items") or []
        if not items:
            return None, None, None
        channel = items[0]
        snippet = channel.get("snippet") or {}
        channel_id = channel.get("id")
        title = snippet.get("title")
        return (
            channel_id if isinstance(channel_id, str) else None,
            title if isinstance(title, str) else None,
            _thumbnail_url(snippet),
        )

    def _ensure_fresh_access_token(self, row: YouTubeCredential) -> str:
        secret = get_settings().jwt_secret
        access = decrypt_secret(row.access_token_encrypted, secret)
        expiry = row.token_expiry
        if expiry is not None and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if expiry is None or expiry - _EXPIRY_SKEW > datetime.now(tz=UTC):
            return access
        if not row.refresh_token_encrypted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="YouTube access expired. Reconnect your channel.",
            )
        user = self.db.get(User, row.user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="YouTube access expired. Reconnect your channel.",
            )
        client_id, client_secret, _redirect = self._require_oauth_config(user)
        refresh = decrypt_secret(row.refresh_token_encrypted, secret)
        payload = self._google_token_request(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            }
        )
        new_access = payload["access_token"]
        row.access_token_encrypted = encrypt_secret(new_access, secret)
        row.token_expiry = datetime.now(tz=UTC) + timedelta(
            seconds=max(int(payload.get("expires_in") or 3600), 60)
        )
        if payload.get("refresh_token"):
            row.refresh_token_encrypted = encrypt_secret(payload["refresh_token"], secret)
        self.db.commit()
        return new_access

    def complete_oauth(
        self,
        *,
        code: str | None,
        state: str | None,
        error: str | None,
    ) -> RedirectResponse:
        if error:
            reason = "cancelled" if error == "access_denied" else "denied"
            logger.info("YouTube OAuth cancelled or denied (%s)", error)
            return self._frontend_redirect(f"youtube={reason}")
        if not code or not state:
            return self._frontend_redirect("youtube=error&reason=missing_code")

        user_id_raw = redis_module.pop_oauth_state(state)
        if not user_id_raw:
            return self._frontend_redirect("youtube=error&reason=invalid_state")
        try:
            user_id = UUID(user_id_raw)
        except ValueError:
            return self._frontend_redirect("youtube=error&reason=invalid_state")

        user = self.db.get(User, user_id)
        if user is None:
            return self._frontend_redirect("youtube=error&reason=unknown_user")

        resolved = self._oauth_client_for(user)
        if resolved is None:
            return self._frontend_redirect("youtube=error&reason=not_configured")
        client_id, client_secret, redirect_uri = resolved
        try:
            tokens = self._google_token_request(
                {
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                }
            )
        except HTTPException as exc:
            reason = (
                "invalid_client"
                if exc.detail == "invalid_client"
                else "token_exchange"
            )
            return self._frontend_redirect(f"youtube=error&reason={reason}")

        access_token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token.strip():
            refresh_token = None
        channel_id, channel_title, thumbnail = self._fetch_channel(access_token)
        self._upsert_credential(
            user_id=user.id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=tokens.get("expires_in"),
            channel_id=channel_id,
            channel_title=channel_title,
            channel_thumbnail_url=thumbnail,
            secret=get_settings().jwt_secret,
        )
        self.db.commit()
        logger.info(
            "YouTube channel connected for user %s channel_id=%s",
            user.id,
            channel_id,
        )
        return self._frontend_redirect("youtube=connected")

    def _revoke_google_token(self, token: str) -> None:
        try:
            with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
                client.post(_GOOGLE_REVOKE_URL, params={"token": token})
        except httpx.HTTPError:
            logger.info("YouTube token revoke request failed; deleting local credential.")

    def disconnect(self, user: User) -> None:
        row = self._credential_for(user.id)
        if row is None:
            return
        secret = get_settings().jwt_secret
        tokens: list[str] = []
        try:
            tokens.append(decrypt_secret(row.access_token_encrypted, secret))
        except ValueError:
            pass
        if row.refresh_token_encrypted:
            try:
                tokens.append(decrypt_secret(row.refresh_token_encrypted, secret))
            except ValueError:
                pass
        for token in tokens:
            self._revoke_google_token(token)
        self.db.delete(row)
        self.db.commit()

    def _youtube_snippet_payload(self, content: Content) -> dict:
        titles = [str(item).strip() for item in (content.titles or []) if str(item).strip()]
        title = (titles[0] if titles else "YouTube Short")[:100]
        tags = []
        for raw in content.hashtags or []:
            tag = str(raw).lstrip("#").strip()
            if tag and tag not in tags:
                tags.append(tag[:30])
            if len(tags) >= 15:
                break
        caption = (content.captions or "").strip()
        hash_line = " ".join(f"#{tag}" for tag in tags)
        description_parts = [part for part in (caption, hash_line) if part]
        if "#shorts" not in " ".join(description_parts).lower():
            description_parts.append("#Shorts")
        description = "\n\n".join(description_parts)[:5000]
        made_for_kids = (get_settings().video_content_style or "").lower() == "kids"
        return {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": "27" if made_for_kids else "22",
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": made_for_kids,
            },
        }

    def _load_video_bytes(self, content: Content) -> bytes:
        storage = StorageService()
        if content.storage_key:
            try:
                return storage.read_bytes(content.storage_key)
            except StorageError as exc:
                logger.warning(
                    "Could not read storage_key for content %s: %s",
                    content.id,
                    exc,
                )
        url = (content.video_url or "").strip()
        if not url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Content has no video file to upload.",
            )
        try:
            with httpx.Client(timeout=_UPLOAD_TIMEOUT) as client:
                response = client.get(url)
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not download the video file for upload.",
            ) from exc
        if response.status_code >= 400 or not response.content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not download the video file for upload.",
            )
        return response.content

    def _upload_video_to_youtube(
        self,
        *,
        access_token: str,
        metadata: dict,
        video_bytes: bytes,
    ) -> str:
        if not video_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Video file is empty.",
            )
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(len(video_bytes)),
        }
        with httpx.Client(timeout=_UPLOAD_TIMEOUT) as client:
            session = client.post(
                _YOUTUBE_UPLOAD_URL,
                params={"uploadType": "resumable", "part": "snippet,status"},
                headers=headers,
                json=metadata,
            )
            if session.status_code >= 400:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=self._youtube_error_message(session, "Could not start YouTube upload."),
                )
            upload_url = session.headers.get("Location")
            if not upload_url:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="YouTube did not return an upload URL.",
                )
            uploaded = client.put(
                upload_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "video/mp4",
                    "Content-Length": str(len(video_bytes)),
                },
                content=video_bytes,
            )
        if uploaded.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=self._youtube_error_message(uploaded, "YouTube rejected the video upload."),
            )
        try:
            payload = uploaded.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="YouTube returned an unreadable upload response.",
            ) from exc
        video_id = payload.get("id") if isinstance(payload, dict) else None
        if not isinstance(video_id, str) or not video_id.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="YouTube did not return a video ID.",
            )
        return video_id.strip()

    def _youtube_error_message(self, response: httpx.Response, fallback: str) -> str:
        try:
            body = response.json()
        except ValueError:
            logger.warning("YouTube upload HTTP %s", response.status_code)
            return fallback
        error = body.get("error") if isinstance(body, dict) else None
        message = None
        reason = None
        if isinstance(error, dict):
            message = error.get("message")
            errors = error.get("errors") or []
            if errors and isinstance(errors[0], dict):
                reason = errors[0].get("reason")
        elif isinstance(error, str):
            reason = error
        logger.warning(
            "YouTube upload HTTP %s reason=%s",
            response.status_code,
            reason or "unknown",
        )
        if reason == "invalid_client":
            return "Google rejected the YouTube client. Re-save the client ID and secret in Settings."
        if reason in {"authError", "unauthorized", "forbidden"}:
            return "YouTube access expired. Reconnect your channel in Settings, then try again."
        if isinstance(message, str) and message.strip():
            return message.strip()[:300]
        return fallback

    def _claim_for_publish(self, content: Content) -> bool:
        """Atomically move content into UPLOADING, guarding against a race.

        Two near-simultaneous publish calls for the same content (e.g. a
        retried n8n webhook alongside a manual click) must not both pass a
        plain Python `if` check and both start an upload. This does the
        check-and-set as a single conditional UPDATE so the database — not
        application code — arbitrates who "wins" the race. Only one caller
        can ever observe rowcount == 1; the loser either learns the upload
        is already in flight (409) or, if it finished in the meantime,
        finds out it's already published and can treat that as success.

        Returns True if this call claimed the row and should proceed to
        upload; False if the content is already published and the caller
        should return it as-is.
        """
        result = self.db.execute(
            update(Content)
            .where(
                Content.id == content.id,
                Content.publish_status.notin_(
                    [PublishStatus.UPLOADING, PublishStatus.PUBLISHED]
                ),
            )
            .values(publish_status=PublishStatus.UPLOADING)
        )
        self.db.commit()
        if result.rowcount == 0:
            # Someone else already claimed it, or it finished publishing in
            # the gap between our earlier fast-path check and now. Refresh
            # to see the real current state and respond accordingly rather
            # than proceeding to a second upload.
            self.db.refresh(content)
            if content.publish_status == PublishStatus.PUBLISHED and content.youtube_video_id:
                return False
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This video is already being published. Please wait for it to finish.",
            )
        content.publish_status = PublishStatus.UPLOADING
        self.db.refresh(content)
        return True

    async def publish_content(self, user: User, content: Content) -> Content:
        if content.status not in _PUBLISHABLE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Approve the video before publishing it to YouTube.",
            )
        if content.publish_status == PublishStatus.PUBLISHED and content.youtube_video_id:
            return content
        if not content.video_url and not content.storage_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Content has no video_url to upload.",
            )
        cred = self._credential_for(user.id)
        if cred is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Connect YouTube in Settings before publishing.",
            )
        try:
            access_token = self._ensure_fresh_access_token(cred)
        except HTTPException:
            raise
        except Exception:
            logger.exception("YouTube token refresh failed during publish for user %s", user.id)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="YouTube access expired. Reconnect your channel in Settings.",
            )

        if not self._claim_for_publish(content):
            return content
        try:
            video_bytes = self._load_video_bytes(content)
            metadata = self._youtube_snippet_payload(content)
            video_id = self._upload_video_to_youtube(
                access_token=access_token,
                metadata=metadata,
                video_bytes=video_bytes,
            )
        except HTTPException:
            content.publish_status = PublishStatus.FAILED
            self.db.commit()
            raise
        except Exception:
            logger.exception("YouTube publish failed for content %s", content.id)
            content.publish_status = PublishStatus.FAILED
            self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="YouTube upload failed. Try publishing again.",
            )

        content.publish_status = PublishStatus.PUBLISHED
        content.youtube_video_id = video_id
        self.db.commit()
        self._record_publish_analytics(user, content, video_id)
        logger.info(
            "Published content %s to YouTube video_id=%s",
            content.id,
            video_id,
        )
        return content

    def _record_publish_analytics(
        self, user: User, content: Content, video_id: str
    ) -> None:
        """Store a real daily snapshot so Analytics is not empty after publish.

        Uses live YouTube statistics when the video is already listed; otherwise
        records zeros (typical for a brand-new upload). Never invents views.
        """
        from app.services.analytics_service import AnalyticsService

        analytics = AnalyticsService(self.db)
        views = likes = comments = 0
        try:
            stats = self.fetch_video_statistics(user, [video_id]).get(video_id)
            if stats is not None:
                views = stats["views"]
                likes = stats["likes"]
                comments = stats["comments"]
        except Exception:
            logger.info(
                "YouTube statistics unavailable immediately after publish for %s",
                content.id,
            )
        analytics.upsert_snapshot(
            content, views=views, likes=likes, comments=comments
        )

    def fetch_video_statistics(
        self, user: User, video_ids: list[str]
    ) -> dict[str, dict[str, int]]:
        """Return {video_id: {views, likes, comments}} from YouTube Data API.

        Prefers the connected channel token, then YOUTUBE_API_KEY for public
        videos. Missing videos are omitted — callers must not invent stats.
        """
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in video_ids:
            video_id = (raw or "").strip()
            if video_id and video_id not in seen:
                seen.add(video_id)
                cleaned.append(video_id)
        if not cleaned:
            return {}
        out: dict[str, dict[str, int]] = {}
        for index in range(0, len(cleaned), 50):
            chunk = cleaned[index : index + 50]
            out.update(self._videos_list_statistics(user, chunk))
        return out

    def _videos_list_statistics(
        self, user: User, video_ids: list[str]
    ) -> dict[str, dict[str, int]]:
        params = {"part": "statistics", "id": ",".join(video_ids), "maxResults": 50}
        headers: dict[str, str] = {}
        token: str | None = None
        cred = self._credential_for(user.id)
        if cred is not None:
            try:
                token = self._ensure_fresh_access_token(cred)
            except Exception:
                logger.info("YouTube OAuth unavailable for statistics; trying API key")
                token = None
        api_key = (get_settings().youtube_api_key or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif api_key:
            params["key"] = api_key
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "YouTube statistics need a connected channel or "
                    "YOUTUBE_API_KEY on the backend."
                ),
            )
        response = self._get_videos_list(params, headers)
        if response.status_code in {401, 403} and token and api_key:
            logger.info("YouTube statistics OAuth was rejected; retrying with API key")
            retry_params = {
                "part": "statistics",
                "id": ",".join(video_ids),
                "maxResults": 50,
                "key": api_key,
            }
            response = self._get_videos_list(retry_params, {})
        if response.status_code >= 400:
            logger.warning(
                "YouTube videos.list statistics HTTP %s", response.status_code
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="YouTube could not return video statistics. Try again shortly.",
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="YouTube returned an unreadable statistics response.",
            ) from exc
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return {}
        results: dict[str, dict[str, int]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            video_id = item.get("id")
            stats = item.get("statistics") or {}
            if not isinstance(video_id, str) or not isinstance(stats, dict):
                continue
            results[video_id] = {
                "views": _int_stat(stats.get("viewCount")),
                "likes": _int_stat(stats.get("likeCount")),
                "comments": _int_stat(stats.get("commentCount")),
            }
        return results

    def _get_videos_list(self, params: dict, headers: dict[str, str]) -> httpx.Response:
        try:
            with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
                return client.get(_YOUTUBE_VIDEOS_URL, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not reach YouTube to load video statistics.",
            ) from exc
