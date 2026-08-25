"""Object/file storage abstraction for generated videos.

Backends:
  local     — filesystem under STORAGE_LOCAL_PATH (dev)
  supabase  — Supabase Storage bucket `videos` (private)
  s3        — reserved / not wired

Never store video blobs in PostgreSQL — only storage_key + URL metadata.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

import httpx

from app.core.config import get_settings

logger = logging.getLogger("creatoros.storage")

SUPABASE_BUCKET = "videos"
_SIGNED_URL_TTL_SECONDS = 60 * 60  # 1 hour for Content Workspace playback


class StorageError(Exception):
    pass


class StorageService:
    def save_bytes(
        self,
        *,
        data: bytes,
        suffix: str = ".mp4",
        prefix: str = "videos",
        owner_id: str | None = None,
        content_type: str = "video/mp4",
    ) -> dict:
        settings = get_settings()
        backend = (settings.storage_backend or "local").lower()

        if backend == "local":
            key = f"{prefix}/{uuid.uuid4()}{suffix}"
            root = Path(settings.storage_local_path)
            path = root / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            base = settings.storage_public_base_url.rstrip("/")
            return {"storage_key": key, "url": f"{base}/{key}"}

        if backend == "supabase":
            return self._save_supabase(
                data=data,
                suffix=suffix,
                owner_id=owner_id,
                content_type=content_type,
            )

        if backend == "s3":
            raise StorageError(
                "STORAGE_BACKEND=s3 is declared but the S3 uploader is not wired "
                "with credentials in this environment."
            )

        raise StorageError(f"Unknown STORAGE_BACKEND '{backend}'.")

    def create_signed_url(
        self, storage_key: str, *, expires_in: int = _SIGNED_URL_TTL_SECONDS
    ) -> str:
        """Return a time-limited URL for private Supabase objects (or local URL)."""
        settings = get_settings()
        backend = (settings.storage_backend or "local").lower()
        if backend == "local":
            base = settings.storage_public_base_url.rstrip("/")
            return f"{base}/{storage_key.lstrip('/')}"
        if backend == "supabase":
            return self._sign_supabase(storage_key, expires_in=expires_in)
        raise StorageError(f"Signed URLs not supported for STORAGE_BACKEND '{backend}'.")

    def read_bytes(self, storage_key: str) -> bytes:
        """Return the stored video bytes. Never invent a file if it is missing."""
        key = (storage_key or "").replace("\\", "/").lstrip("/")
        if not key or ".." in key.split("/"):
            raise StorageError("Invalid storage key.")
        settings = get_settings()
        backend = (settings.storage_backend or "local").lower()
        if backend == "local":
            path = (Path(settings.storage_local_path) / key).resolve()
            root = Path(settings.storage_local_path).resolve()
            if root not in path.parents and path != root:
                raise StorageError("Invalid storage key.")
            if not path.is_file():
                raise StorageError("Video file is missing from storage.")
            data = path.read_bytes()
            if not data:
                raise StorageError("Video file is empty.")
            return data
        if backend == "supabase":
            return self._read_supabase(key)
        raise StorageError(f"Reading videos is not supported for STORAGE_BACKEND '{backend}'.")

    def _read_supabase(self, storage_key: str) -> bytes:
        url, key = self._supabase_config()
        path = storage_key
        if path.startswith(f"{SUPABASE_BUCKET}/"):
            path = path[len(SUPABASE_BUCKET) + 1 :]
        resp = httpx.get(
            f"{url}/storage/v1/object/{SUPABASE_BUCKET}/{path}",
            headers=self._supabase_headers(key),
            timeout=httpx.Timeout(connect=30.0, read=120.0, write=30.0, pool=30.0),
        )
        if resp.status_code >= 400:
            raise StorageError(
                f"Supabase download failed HTTP {resp.status_code}: "
                f"{(resp.text or '')[:300]}"
            )
        if not resp.content:
            raise StorageError("Video file is empty.")
        return resp.content

    def assert_owner_path(self, storage_key: str, owner_id: str) -> None:
        """Reject keys that are not under the owner's folder (path-level ACL)."""
        # Canonical key: videos/{user_id}/{file}.mp4
        if not storage_key.startswith(f"{SUPABASE_BUCKET}/{owner_id}/"):
            raise StorageError("Storage key does not belong to this user.")

    def _supabase_config(self) -> tuple[str, str]:
        settings = get_settings()
        url = (settings.supabase_url or "").rstrip("/")
        # Secret/service key required for bucket admin + private uploads (bypasses RLS).
        key = (
            (settings.supabase_secret_key or "").strip()
            or (settings.supabase_key or "").strip()
        )
        if not url or not key:
            raise StorageError(
                "Supabase Storage is not configured. Set SUPABASE_URL and "
                "SUPABASE_SECRET_KEY (service/secret key) in the backend environment. "
                "The publishable key alone cannot create buckets or upload privately."
            )
        if key.startswith("sb_publishable_"):
            raise StorageError(
                "SUPABASE_SECRET_KEY must be the secret/service_role key "
                "(sb_secret_... or legacy service_role JWT), not the publishable key. "
                "Publishable keys cannot bypass Storage RLS."
            )
        return url, key

    def _supabase_headers(self, key: str, *, content_type: str | None = None) -> dict:
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def ensure_videos_bucket(self) -> None:
        """Create private `videos` bucket if missing."""
        url, key = self._supabase_config()
        headers = self._supabase_headers(key, content_type="application/json")
        list_resp = httpx.get(f"{url}/storage/v1/bucket", headers=headers, timeout=30.0)
        if list_resp.status_code >= 400:
            raise StorageError(
                f"Failed to list Supabase buckets HTTP {list_resp.status_code}: "
                f"{(list_resp.text or '')[:300]}"
            )
        buckets = list_resp.json()
        names = {
            (b.get("id") or b.get("name"))
            for b in buckets
            if isinstance(b, dict)
        }
        if SUPABASE_BUCKET in names:
            return

        # Omit file_size_limit — values above the project's plan max return HTTP 400/413.
        create = httpx.post(
            f"{url}/storage/v1/bucket",
            headers=headers,
            json={
                "id": SUPABASE_BUCKET,
                "name": SUPABASE_BUCKET,
                "public": False,
                "allowed_mime_types": ["video/mp4", "video/quicktime"],
            },
            timeout=30.0,
        )
        if create.status_code in {200, 201}:
            logger.info("Created Supabase Storage bucket '%s'", SUPABASE_BUCKET)
            return
        # Race: another process created it.
        if create.status_code == 400 and "already exists" in (create.text or "").lower():
            return
        raise StorageError(
            f"Failed to create Supabase bucket '{SUPABASE_BUCKET}' "
            f"HTTP {create.status_code}: {(create.text or '')[:300]}"
        )

    def _save_supabase(
        self,
        *,
        data: bytes,
        suffix: str,
        owner_id: str | None,
        content_type: str,
    ) -> dict:
        if not owner_id:
            raise StorageError(
                "owner_id is required for Supabase video storage so objects "
                "can be scoped per user."
            )
        if not data:
            raise StorageError("Refusing to upload empty video bytes.")

        self.ensure_videos_bucket()
        url, key = self._supabase_config()
        object_name = f"{owner_id}/{uuid.uuid4()}{suffix}"
        # Canonical key stored in Postgres (not a blob).
        storage_key = f"{SUPABASE_BUCKET}/{object_name}"

        upload = httpx.post(
            f"{url}/storage/v1/object/{SUPABASE_BUCKET}/{object_name}",
            headers={
                **self._supabase_headers(key),
                "Content-Type": content_type,
                "x-upsert": "true",
            },
            content=data,
            timeout=httpx.Timeout(connect=30.0, read=120.0, write=300.0, pool=30.0),
        )
        if upload.status_code >= 400:
            raise StorageError(
                f"Supabase upload failed HTTP {upload.status_code}: "
                f"{(upload.text or '')[:300]}"
            )

        signed = self._sign_supabase(storage_key, expires_in=_SIGNED_URL_TTL_SECONDS)
        logger.info(
            "Uploaded video to Supabase Storage key=%s bytes=%s",
            storage_key,
            len(data),
        )
        return {"storage_key": storage_key, "url": signed}

    def _sign_supabase(self, storage_key: str, *, expires_in: int) -> str:
        url, key = self._supabase_config()
        # storage_key is "videos/{user}/{file}.mp4" — strip bucket for sign path.
        path = storage_key
        if path.startswith(f"{SUPABASE_BUCKET}/"):
            path = path[len(SUPABASE_BUCKET) + 1 :]
        resp = httpx.post(
            f"{url}/storage/v1/object/sign/{SUPABASE_BUCKET}/{path}",
            headers=self._supabase_headers(key, content_type="application/json"),
            json={"expiresIn": expires_in},
            timeout=30.0,
        )
        if resp.status_code >= 400:
            raise StorageError(
                f"Supabase signed URL failed HTTP {resp.status_code}: "
                f"{(resp.text or '')[:300]}"
            )
        body = resp.json()
        signed_path = body.get("signedURL") or body.get("signedUrl") or body.get("url")
        if not signed_path:
            raise StorageError("Supabase signed URL response missing signedURL.")
        if signed_path.startswith("http"):
            return signed_path
        return f"{url}/storage/v1{signed_path}"
