"""Redis-backed automation job store (M5).

Jobs are opaque JSON blobs under `automation:job:{id}`. Idempotency keys map
to an existing job id under `automation:idempotency:{key}` so n8n retries do
not spawn duplicate content generations.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from redis.exceptions import RedisError

from app.core import redis as redis_module
from app.core.config import get_settings
from app.core.redis import RedisUnavailableError

JOB_STATUSES = ("queued", "running", "completed", "failed")


class JobStore:
    def __init__(self) -> None:
        self._ttl = get_settings().automation_job_ttl_seconds
        self._stale_seconds = get_settings().automation_job_stale_seconds

    def create(
        self,
        *,
        kind: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        job_id = str(uuid.uuid4())
        if idempotency_key:
            # Claim the idempotency key first (SET NX). Concurrent n8n retries
            # share one job id instead of spawning duplicate generations.
            claimed = self._claim_idempotent(idempotency_key, job_id)
            if not claimed:
                existing_id = self._get_idempotent(idempotency_key)
                if existing_id:
                    existing = self.get(existing_id)
                    if existing is not None:
                        existing["idempotent_replay"] = True
                        return existing
                    job_id = existing_id

        job = {
            "job_id": job_id,
            "kind": kind,
            "status": "queued",
            "payload": payload,
            "content_id": None,
            "result": None,
            "error": None,
            "created_at": datetime.now(tz=UTC).isoformat(),
            "updated_at": datetime.now(tz=UTC).isoformat(),
        }
        self._set(job_id, job, track_recent=True)
        return job

    def get(self, job_id: str) -> dict[str, Any] | None:
        try:
            raw = redis_module.redis_client.get(f"automation:job:{job_id}")
        except RedisError as exc:
            raise RedisUnavailableError() from exc
        if not raw:
            return None
        return self._maybe_reap(json.loads(raw))

    def _maybe_reap(self, job: dict[str, Any]) -> dict[str, Any]:
        """Auto-fail a job stuck in "running" with no progress.

        In-process background tasks don't survive a backend process
        restart or crash: if that happens mid-job, the job would otherwise
        stay "running" in Redis forever, and n8n (or the in-app Automation
        page) would poll it indefinitely with no way to know it needs to
        retry. Any read of a job that has been "running" for longer than
        AUTOMATION_JOB_STALE_SECONDS with no status update is treated as
        abandoned and flipped to "failed" here, lazily, on read — no
        separate scheduler/cron process required.
        """
        if job.get("status") != "running":
            return job
        updated_at = job.get("updated_at")
        if not updated_at:
            return job
        try:
            updated_dt = datetime.fromisoformat(updated_at)
        except ValueError:
            return job
        if updated_dt.tzinfo is None:
            updated_dt = updated_dt.replace(tzinfo=UTC)
        age_seconds = (datetime.now(tz=UTC) - updated_dt).total_seconds()
        if age_seconds <= self._stale_seconds:
            return job
        job["status"] = "failed"
        job["error"] = (
            "Job timed out: no progress recorded for over "
            f"{int(self._stale_seconds)}s. The backend worker likely "
            "restarted or crashed mid-job. Safe to retry — re-trigger with "
            "a new Idempotency-Key."
        )
        job["updated_at"] = datetime.now(tz=UTC).isoformat()
        try:
            self._set(job["job_id"], job)
        except RedisUnavailableError:
            # Best-effort: still return the reaped view to this caller even
            # if we couldn't persist it; the next successful read will
            # reap it again.
            pass
        return job

    def update(self, job_id: str, **fields: Any) -> dict[str, Any]:
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        job.update(fields)
        job["updated_at"] = datetime.now(tz=UTC).isoformat()
        self._set(job_id, job)
        return job

    def recent(self, limit: int = 10) -> list[dict[str, Any]]:
        """Best-effort recent jobs for the Automation status UI.

        Uses a Redis list index written alongside each create. Failures here
        must never break job execution.
        """
        try:
            ids = redis_module.redis_client.lrange("automation:jobs:recent", 0, max(0, limit - 1))
        except RedisError:
            return []
        jobs: list[dict[str, Any]] = []
        for job_id in ids:
            job = self.get(job_id)
            if job:
                jobs.append(job)
        return jobs

    def _set(self, job_id: str, job: dict[str, Any], *, track_recent: bool = False) -> None:
        try:
            redis_module.redis_client.setex(
                # `default=str` is a deliberate safety net: job "result"
                # payloads come from service-layer methods (e.g.
                # AnalyticsService.run_coach) that return UUIDs/dates as
                # native Python objects rather than pre-serialized
                # primitives. Without this, any such field would raise
                # TypeError deep inside a background task and silently
                # flip an otherwise-successful job to "failed".
                f"automation:job:{job_id}", self._ttl, json.dumps(job, default=str)
            )
            if track_recent:
                redis_module.redis_client.lpush("automation:jobs:recent", job_id)
                redis_module.redis_client.ltrim("automation:jobs:recent", 0, 49)
                redis_module.redis_client.expire("automation:jobs:recent", self._ttl)
        except RedisError as exc:
            raise RedisUnavailableError() from exc

    def _get_idempotent(self, key: str) -> str | None:
        try:
            value = redis_module.redis_client.get(f"automation:idempotency:{key}")
        except RedisError as exc:
            raise RedisUnavailableError() from exc
        return value

    def _claim_idempotent(self, key: str, job_id: str) -> bool:
        try:
            # NX: first writer wins — concurrent retries share one job.
            return bool(
                redis_module.redis_client.set(
                    f"automation:idempotency:{key}",
                    job_id,
                    ex=self._ttl,
                    nx=True,
                )
            )
        except RedisError as exc:
            raise RedisUnavailableError() from exc
