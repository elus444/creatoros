"""M5 automation API tests — n8n webhook auth, async jobs, idempotency."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.schemas.agent_outputs import ResearchOutput, StrategyOutput, VideoOutput
from app.services.collectors import CollectedItem
from app.services.collectors.youtube_collector import YouTubeCollector
from app.services.llm_service import LLMResult, LLMService
from tests.video_pipeline_fakes import install_fake_video_provider

VALID_RESEARCH = {
    "summary": "Automation research summary.",
    "facts": ["Fact one"],
    "audience_insights": ["Insight one"],
    "opportunities": ["Opportunity one"],
}
VALID_STRATEGY = {
    "angle": "Automation angle",
    "hooks": ["Hook one"],
    "target_audience": "Creators",
    "structure": ["hook", "body", "cta"],
}
VALID_VIDEO = {
    "concept": "Automation concept",
    "scenes": ["s1", "s2"],
    "visual_direction": "clean",
    "narration": "Automation generated script.",
    "titles": ["Automation Title"],
    "caption": "Automation caption",
    "hashtags": ["automation"],
    "aspect_ratio": "9:16",
    "duration_seconds": 10,
}


def _llm_result(data: dict) -> LLMResult:
    return LLMResult(
        data=data,
        raw_text=str(data),
        model="test",
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
    )


def _install_fake_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_video_provider(monkeypatch)
    script = {
        ResearchOutput: [_llm_result(VALID_RESEARCH)],
        StrategyOutput: [_llm_result(VALID_STRATEGY)],
        VideoOutput: [_llm_result(VALID_VIDEO)],
    }

    async def fake_generate_structured(
        self, *, prompt, response_model, system_instruction=None, temperature=0.4
    ):
        items = script.get(response_model)
        if not items:
            raise AssertionError(f"No scripted response for {response_model}")
        return items.pop(0)

    monkeypatch.setattr(LLMService, "generate_structured", fake_generate_structured)


def _create_project(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/projects",
        json={"name": "Auto Project", "niche": "youtube shorts tips"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_automation_collect_requires_secret(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    project_id = _create_project(client, auth_headers)
    response = client.post(
        "/api/v1/automation/trends/collect",
        json={"project_id": project_id},
    )
    assert response.status_code == 401


def test_automation_collect_rejects_bad_secret(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    project_id = _create_project(client, auth_headers)
    response = client.post(
        "/api/v1/automation/trends/collect",
        json={"project_id": project_id},
        headers={"X-Automation-Secret": "wrong"},
    )
    assert response.status_code == 401


def test_automation_collect_runs_existing_trend_pipeline(
    client: TestClient,
    auth_headers: dict[str, str],
    automation_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = _create_project(client, auth_headers)

    async def fake_youtube_collect(self, query, limit=10, **kwargs):
        return [
            CollectedItem(
                title="How to make kids pasta Shorts",
                source="youtube",
                url="https://www.youtube.com/shorts/auto1",
                published_at=datetime.now(tz=UTC),
                metrics={"views": 1000, "likes": 10, "comments": 1},
                default_audio_language="en",
            )
        ]

    monkeypatch.setattr(YouTubeCollector, "collect", fake_youtube_collect)

    accepted = client.post(
        "/api/v1/automation/trends/collect",
        json={"project_id": project_id},
        headers=automation_headers,
    )
    assert accepted.status_code == 200
    body = accepted.json()
    assert body["success"] is True
    assert body["status"] == "queued"
    job_id = body["job_id"]

    status = client.get(
        f"/api/v1/automation/jobs/{job_id}", headers=automation_headers
    )
    assert status.status_code == 200
    job = status.json()
    assert job["status"] == "completed"
    assert job["kind"] == "trends.collect"
    assert job["result"]["collected"] == 1

    trends = client.get(f"/api/v1/projects/{project_id}/trends", headers=auth_headers)
    assert len(trends.json()) == 1


def test_automation_content_generate_job_completes(
    client: TestClient,
    auth_headers: dict[str, str],
    automation_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = _create_project(client, auth_headers)

    async def fake_youtube_collect(self, query, limit=10, **kwargs):
        return [
            CollectedItem(
                title="How to make kids counting Shorts",
                source="youtube",
                url="https://www.youtube.com/shorts/gen1",
                published_at=datetime.now(tz=UTC),
                metrics={"views": 5000, "likes": 50, "comments": 5},
                default_audio_language="en",
            )
        ]

    monkeypatch.setattr(YouTubeCollector, "collect", fake_youtube_collect)
    client.post(
        f"/api/v1/projects/{project_id}/trends/collect", headers=auth_headers
    )
    _install_fake_llm(monkeypatch)

    accepted = client.post(
        "/api/v1/automation/content/generate",
        json={"project_id": project_id},
        headers=automation_headers,
    )
    assert accepted.status_code == 200
    job_id = accepted.json()["job_id"]

    job = client.get(
        f"/api/v1/automation/jobs/{job_id}", headers=automation_headers
    ).json()
    assert job["status"] == "completed"
    assert job["content_id"]


def test_automation_idempotency_reuses_job(
    client: TestClient,
    auth_headers: dict[str, str],
    automation_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = _create_project(client, auth_headers)

    async def fake_youtube_collect(self, query, limit=10, **kwargs):
        return [
            CollectedItem(
                title="How to make kids meal prep Shorts",
                source="youtube",
                url="https://www.youtube.com/shorts/idem1",
                published_at=datetime.now(tz=UTC),
                metrics={"views": 100, "likes": 1, "comments": 0},
                default_audio_language="en",
            )
        ]

    monkeypatch.setattr(YouTubeCollector, "collect", fake_youtube_collect)
    client.post(
        f"/api/v1/projects/{project_id}/trends/collect", headers=auth_headers
    )
    _install_fake_llm(monkeypatch)

    headers = {**automation_headers, "Idempotency-Key": "daily-2026-08-10"}
    first = client.post(
        "/api/v1/automation/content/generate",
        json={"project_id": project_id},
        headers=headers,
    ).json()
    second = client.post(
        "/api/v1/automation/content/generate",
        json={"project_id": project_id},
        headers=headers,
    ).json()
    assert first["job_id"] == second["job_id"]
    assert second["idempotent_replay"] is True


def test_automation_status_requires_jwt(
    client: TestClient, automation_headers: dict[str, str]
) -> None:
    response = client.get("/api/v1/automation/status", headers=automation_headers)
    assert response.status_code == 401


def test_automation_status_for_user(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get("/api/v1/automation/status", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["automation_configured"] is True


def test_automation_status_does_not_expose_another_users_jobs(
    client: TestClient,
    auth_headers: dict[str, str],
    automation_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    accepted = client.post(
        "/api/v1/automation/trends/collect",
        json={"project_id": project_id},
        headers=automation_headers,
    )
    assert accepted.status_code == 200

    other = client.post(
        "/api/v1/auth/register",
        json={"email": "automation-viewer@example.com", "password": "securepass1"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}

    owner_status = client.get("/api/v1/automation/status", headers=auth_headers)
    assert owner_status.status_code == 200
    assert [job["job_id"] for job in owner_status.json()["recent_jobs"]] == [
        accepted.json()["job_id"]
    ]

    other_status = client.get("/api/v1/automation/status", headers=other_headers)
    assert other_status.status_code == 200
    assert other_status.json()["recent_jobs"] == []


def test_automation_publish_requires_secret(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.test_content_workspace import _create_generated_content

    created = _create_generated_content(client, auth_headers, monkeypatch)
    response = client.post(f"/api/v1/automation/content/{created['id']}/publish")
    assert response.status_code == 401


def test_automation_publish_job_completes(
    client: TestClient,
    auth_headers: dict[str, str],
    automation_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """n8n triggers publish via the shared secret (no user JWT involved),
    proving content -> project -> owner resolution works end to end.
    """
    from app.models.user import User
    from app.services.youtube_service import YouTubeService
    from tests.test_content_workspace import _create_generated_content
    from tests.test_youtube_oauth import _enable_oauth

    _enable_oauth(monkeypatch)
    created = _create_generated_content(client, auth_headers, monkeypatch)
    content_id = created["id"]

    review = client.post(f"/api/v1/content/{content_id}/review", headers=auth_headers)
    assert review.status_code == 200
    approve = client.post(f"/api/v1/content/{content_id}/approve", headers=auth_headers)
    assert approve.status_code == 200

    db = client.session_local()
    try:
        user = db.query(User).one()
        YouTubeService(db).store_tokens_for_tests(
            user,
            access_token="ya29.access-secret",
            refresh_token="1//refresh-secret",
            channel_id="UCabc",
            channel_title="Automation Channel",
        )
    finally:
        db.close()

    monkeypatch.setattr(
        YouTubeService, "_load_video_bytes", lambda self, content: b"fake-mp4-bytes"
    )
    monkeypatch.setattr(
        YouTubeService,
        "_upload_video_to_youtube",
        lambda self, *, access_token, metadata, video_bytes: "autoSHORTS1",
    )
    monkeypatch.setattr(
        YouTubeService,
        "fetch_video_statistics",
        lambda self, user, ids: {vid: {"views": 0, "likes": 0, "comments": 0} for vid in ids},
    )

    accepted = client.post(
        f"/api/v1/automation/content/{content_id}/publish",
        headers=automation_headers,
    )
    assert accepted.status_code == 200
    job_id = accepted.json()["job_id"]

    job = client.get(
        f"/api/v1/automation/jobs/{job_id}", headers=automation_headers
    ).json()
    assert job["status"] == "completed"
    assert job["kind"] == "content.publish"
    assert job["result"]["youtube_video_id"] == "autoSHORTS1"

    status_body = client.get(f"/api/v1/content/{content_id}", headers=auth_headers).json()
    assert status_body["publish_status"] == "published"
    assert status_body["youtube_video_id"] == "autoSHORTS1"


def test_automation_publish_unknown_content_returns_404(
    client: TestClient, automation_headers: dict[str, str]
) -> None:
    import uuid

    response = client.post(
        f"/api/v1/automation/content/{uuid.uuid4()}/publish",
        headers=automation_headers,
    )
    assert response.status_code == 404


def test_automation_analytics_ingest_upserts(
    client: TestClient,
    auth_headers: dict[str, str],
    automation_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.test_content_workspace import _create_generated_content

    created = _create_generated_content(client, auth_headers, monkeypatch)
    content_id = created["id"]

    first = client.post(
        "/api/v1/automation/analytics/ingest",
        json={
            "content_id": content_id,
            "views": 100,
            "likes": 10,
            "comments": 2,
            "date": "2026-08-01",
        },
        headers=automation_headers,
    )
    assert first.status_code == 200
    assert first.json()["views"] == 100

    # Same (content_id, date) again — must upsert, not duplicate.
    second = client.post(
        "/api/v1/automation/analytics/ingest",
        json={
            "content_id": content_id,
            "views": 250,
            "likes": 20,
            "comments": 4,
            "date": "2026-08-01",
        },
        headers=automation_headers,
    )
    assert second.status_code == 200
    assert second.json()["views"] == 250
    assert second.json()["id"] == first.json()["id"]

    summary = client.get(
        f"/api/v1/analytics/projects/{created['project_id']}?range_days=30",
        headers=auth_headers,
    )
    assert summary.status_code == 200
    assert summary.json()["totals"]["views"] == 250


def test_automation_analytics_ingest_requires_secret(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.test_content_workspace import _create_generated_content

    created = _create_generated_content(client, auth_headers, monkeypatch)
    response = client.post(
        "/api/v1/automation/analytics/ingest",
        json={
            "content_id": created["id"],
            "views": 1,
            "likes": 0,
            "comments": 0,
            "date": "2026-08-01",
        },
    )
    assert response.status_code == 401


def test_automation_coach_job_reports_insufficient_data(
    client: TestClient,
    auth_headers: dict[str, str],
    automation_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)

    accepted = client.post(
        f"/api/v1/automation/projects/{project_id}/coach",
        json={"range_days": 30},
        headers=automation_headers,
    )
    assert accepted.status_code == 200
    job_id = accepted.json()["job_id"]

    job = client.get(
        f"/api/v1/automation/jobs/{job_id}", headers=automation_headers
    ).json()
    assert job["status"] == "completed"
    assert job["kind"] == "analytics.coach"
    # No published content with metrics yet — coach must say so rather
    # than fail or hallucinate recommendations.
    assert job["result"]["status"] == "insufficient_data"


def test_automation_coach_requires_secret(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    project_id = _create_project(client, auth_headers)
    response = client.post(f"/api/v1/automation/projects/{project_id}/coach")
    assert response.status_code == 401


def test_job_reaper_fails_stuck_running_job(
    client: TestClient, automation_headers: dict[str, str]
) -> None:
    """A job that has been "running" for longer than
    AUTOMATION_JOB_STALE_SECONDS with no update (simulating a backend
    crash/restart mid-job) must be auto-reaped to "failed" on the next
    read, rather than staying "running" forever with nothing able to
    retry it.
    """
    from app.services.job_store import JobStore

    store = JobStore()
    job = store.create(kind="content.generate", payload={}, idempotency_key=None)
    store.update(job["job_id"], status="running")

    # Simulate time passing with no progress by backdating updated_at past
    # the stale threshold directly in the stored record.
    import json

    from app.core import redis as redis_module

    key = f"automation:job:{job['job_id']}"
    raw = json.loads(redis_module.redis_client.get(key))
    raw["updated_at"] = "2020-01-01T00:00:00+00:00"
    redis_module.redis_client.setex(key, 3600, json.dumps(raw))

    reaped = store.get(job["job_id"])
    assert reaped is not None
    assert reaped["status"] == "failed"
    assert "timed out" in reaped["error"].lower()

    # And the reaped state is what a subsequent poll (e.g. n8n) sees too.
    response = client.get(
        f"/api/v1/automation/jobs/{job['job_id']}", headers=automation_headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "failed"


def test_job_reaper_leaves_fresh_running_job_alone(client: TestClient) -> None:
    from app.services.job_store import JobStore

    store = JobStore()
    job = store.create(kind="trends.collect", payload={}, idempotency_key=None)
    store.update(job["job_id"], status="running")

    reaped = store.get(job["job_id"])
    assert reaped is not None
    assert reaped["status"] == "running"


@pytest.mark.asyncio
async def test_notify_job_event_noop_without_webhook_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No N8N_NOTIFY_WEBHOOK_URL configured -> no HTTP call attempted at all."""
    from app.core.config import Settings
    from app.services import notification_service

    monkeypatch.setattr(
        notification_service, "get_settings", lambda: Settings(n8n_notify_webhook_url=None)
    )

    called = False

    class _ExplodingClient:
        def __init__(self, *a, **kw):
            nonlocal called
            called = True

    monkeypatch.setattr(notification_service.httpx, "AsyncClient", _ExplodingClient)

    await notification_service.notify_job_event(
        event="content.generate.completed",
        job_id="abc",
        kind="content.generate",
        status="completed",
    )
    assert called is False


@pytest.mark.asyncio
async def test_notify_job_event_posts_signed_payload_and_survives_uuid_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test: a `result` dict containing a native UUID (as
    AnalyticsService.run_coach returns) must not raise — this is the exact
    bug the JSON `default=str` fix addresses.
    """
    import uuid

    from app.core.config import Settings
    from app.services import notification_service

    monkeypatch.setattr(
        notification_service,
        "get_settings",
        lambda: Settings(
            n8n_notify_webhook_url="https://n8n.example.com/webhook/creatoros",
            n8n_webhook_secret="shh-secret",
        ),
    )

    captured: dict = {}

    class _FakeResponse:
        status_code = 200

    class _FakeAsyncClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, content=None, headers=None, **kw):
            captured["url"] = url
            captured["content"] = content
            captured["headers"] = headers
            return _FakeResponse()

    monkeypatch.setattr(notification_service.httpx, "AsyncClient", _FakeAsyncClient)

    await notification_service.notify_job_event(
        event="analytics.coach.ready",
        job_id="job-1",
        kind="analytics.coach",
        status="completed",
        project_id=str(uuid.uuid4()),
        result={"project_id": uuid.uuid4(), "status": "ready"},
    )

    assert captured["url"] == "https://n8n.example.com/webhook/creatoros"
    assert captured["headers"]["X-Automation-Secret"] == "shh-secret"
    import json as _json

    body = _json.loads(captured["content"])
    assert body["event"] == "analytics.coach.ready"
    assert isinstance(body["result"]["project_id"], str)

