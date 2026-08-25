"""Outbound n8n notifications (M5/M10).

Fires a signed webhook POST to N8N_NOTIFY_WEBHOOK_URL when an automation
job finishes (success or failure), so n8n workflows can react to
completion instead of only polling GET /automation/jobs/{id}.

This is deliberately best-effort and side-channel: a notification failure
must never fail, retry, or roll back the underlying job. The job's status
in Redis (readable via /automation/jobs/{id}) is always the source of
truth; the webhook is a convenience trigger on top of it.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger("creatoros.notifications")


async def notify_job_event(
    *,
    event: str,
    job_id: str,
    kind: str,
    status: str,
    project_id: str | None = None,
    content_id: str | None = None,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    """Best-effort webhook notification. Never raises.

    `event` is a stable name like "content.generate.completed" or
    "content.publish.failed" — safe for an n8n IF/Switch node to branch on.
    """
    settings = get_settings()
    url = settings.n8n_notify_webhook_url
    if not url:
        return

    payload = {
        "event": event,
        "job_id": job_id,
        "kind": kind,
        "status": status,
        "project_id": project_id,
        "content_id": content_id,
        "result": result,
        "error": error,
    }
    headers = {"Content-Type": "application/json"}
    if settings.n8n_webhook_secret:
        # Lets the receiving n8n workflow verify this call actually came
        # from this backend, using the same shared secret n8n itself sends
        # us on inbound calls.
        headers["X-Automation-Secret"] = settings.n8n_webhook_secret

    try:
        # Use default=str (not json=payload) since `result` can contain
        # native UUID/date objects straight from a service-layer return
        # value — stdlib json can't serialize those, and this call must
        # never raise regardless.
        body = json.dumps(payload, default=str).encode("utf-8")
        async with httpx.AsyncClient(timeout=settings.n8n_notify_timeout_seconds) as client:
            response = await client.post(url, content=body, headers=headers)
            if response.status_code >= 400:
                logger.warning(
                    "n8n notify webhook returned HTTP %s for event=%s job_id=%s",
                    response.status_code,
                    event,
                    job_id,
                )
    except Exception:
        # Notification delivery is never allowed to affect job outcome —
        # log and move on. n8n can still poll the job status endpoint.
        logger.warning(
            "n8n notify webhook delivery failed for event=%s job_id=%s",
            event,
            job_id,
            exc_info=True,
        )
