"""Per-user video provider integrations. API keys never leave the server."""

from __future__ import annotations

import logging
import re
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.models.user import User
from app.models.video_provider_credential import VideoProviderCredential

logger = logging.getLogger("creatoros.integrations")

SUPPORTED_PROVIDERS = ("replicate",)
_REPLICATE_ACCOUNT_URL = "https://api.replicate.com/v1/account"
_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")
_HTTP_TIMEOUT = 15.0


def _vault_secret() -> str:
    return get_settings().jwt_secret


class IntegrationService:
    def __init__(self, db: Session):
        self.db = db

    def _row_for(self, user_id: UUID) -> VideoProviderCredential | None:
        return self.db.scalars(
            select(VideoProviderCredential).where(
                VideoProviderCredential.user_id == user_id
            )
        ).first()

    def _decrypt_key(self, row: VideoProviderCredential) -> str | None:
        try:
            return decrypt_secret(row.api_key_encrypted, _vault_secret()).strip() or None
        except ValueError:
            logger.warning(
                "Stored video provider secret could not be decrypted for user %s",
                row.user_id,
            )
            return None

    def public_status(self, user: User) -> dict:
        row = self._row_for(user.id)
        has_key = False
        provider = "replicate"
        model_id = None
        source = None
        if row is not None:
            provider = row.provider
            model_id = row.model_id
            has_key = self._decrypt_key(row) is not None
            if has_key:
                source = "settings"
        env_token = (get_settings().replicate_api_token or "").strip()
        if source is None and env_token:
            source = "env"
            has_key = True
            provider = "replicate"
        return {
            "provider": provider,
            "supported_providers": [
                {"id": "replicate", "label": "Replicate"},
            ],
            "model_id": model_id,
            "has_key": has_key,
            "configured": has_key,
            "source": source,
        }

    def save(
        self,
        user: User,
        *,
        provider: str,
        model_id: str | None,
        api_key: str | None,
    ) -> dict:
        provider = (provider or "").strip().lower()
        if provider not in SUPPORTED_PROVIDERS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported video provider. Start with Replicate.",
            )
        cleaned_model = (model_id or "").strip() or None
        if cleaned_model and not _MODEL_ID_RE.fullmatch(cleaned_model):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Model ID contains invalid characters.",
            )
        secret_in = (api_key or "").strip()
        row = self._row_for(user.id)
        if not secret_in and row is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A provider API key is required.",
            )
        vault = _vault_secret()
        if secret_in:
            encrypted = encrypt_secret(secret_in, vault)
            if decrypt_secret(encrypted, vault) != secret_in:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Could not store the provider API key securely. Try again.",
                )
        else:
            encrypted = row.api_key_encrypted if row is not None else None
        if encrypted is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A provider API key is required.",
            )
        if row is None:
            row = VideoProviderCredential(
                user_id=user.id,
                provider=provider,
                model_id=cleaned_model,
                api_key_encrypted=encrypted,
            )
            self.db.add(row)
        else:
            if row.user_id != user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not allowed to change these credentials.",
                )
            row.provider = provider
            row.model_id = cleaned_model
            if secret_in:
                row.api_key_encrypted = encrypted
        self.db.commit()
        return self.public_status(user)

    def delete(self, user: User) -> None:
        row = self._row_for(user.id)
        if row is None:
            return
        if row.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to change these credentials.",
            )
        self.db.delete(row)
        self.db.commit()

    def resolved_credentials(self, user_id: UUID) -> dict | None:
        """Return decrypted provider settings owned by this user, or None."""
        row = self._row_for(user_id)
        if row is None or row.user_id != user_id:
            return None
        api_key = self._decrypt_key(row)
        if not api_key:
            return None
        return {
            "provider": row.provider,
            "api_key": api_key,
            "model_id": row.model_id,
        }

    async def test_connection(
        self,
        user: User,
        *,
        provider: str,
        api_key: str | None,
    ) -> dict:
        provider = (provider or "").strip().lower()
        if provider not in SUPPORTED_PROVIDERS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported video provider. Start with Replicate.",
            )
        token = (api_key or "").strip()
        if not token:
            stored = self.resolved_credentials(user.id)
            if stored and stored["provider"] == provider:
                token = stored["api_key"]
        if not token:
            env_token = (get_settings().replicate_api_token or "").strip()
            if provider == "replicate" and env_token:
                token = env_token
        if not token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Enter an API key, or save one first, then test the connection.",
            )
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                response = await client.get(
                    _REPLICATE_ACCOUNT_URL,
                    headers={"Authorization": f"Bearer {token}"},
                )
        except httpx.HTTPError:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not reach Replicate. Try again shortly.",
            ) from None
        if response.status_code in {401, 403}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Replicate rejected this API key.",
            )
        if response.status_code == 429:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Replicate rate limit exceeded. Try again shortly.",
            )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Replicate could not verify this key. Try again shortly.",
            )
        username = None
        try:
            payload = response.json()
            raw_name = payload.get("username") or payload.get("name")
            if isinstance(raw_name, str) and raw_name.strip():
                username = raw_name.strip()[:80]
        except ValueError:
            username = None
        return {
            "ok": True,
            "provider": "replicate",
            "account": username,
            "message": "Replicate connection succeeded.",
        }
