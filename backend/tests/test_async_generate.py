"""Async generate returns immediately with a job id (performance path)."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.services.collectors import CollectedItem
from app.services.collectors.youtube_collector import YouTubeCollector
from tests.video_pipeline_fakes import (
    full_pipeline_script,
    install_fake_llm,
    install_fake_video_provider,
)


def test_async_generate_returns_202_and_job(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fake_video_provider(monkeypatch)
    install_fake_llm(monkeypatch, full_pipeline_script())

    project = client.post(
        "/api/v1/projects",
        json={"name": "Async Channel", "niche": "ai tools"},
        headers=auth_headers,
    ).json()

    async def fake_youtube_collect(self, query, limit=10, **kwargs):
        return [
            CollectedItem(
                title="How to grow YouTube Shorts with AI tools",
                source="youtube",
                url="https://www.youtube.com/shorts/async1",
                published_at=datetime.now(tz=UTC),
                metrics={"views": 10_000, "likes": 100, "comments": 10},
                default_audio_language="en",
            )
        ]

    monkeypatch.setattr(YouTubeCollector, "collect", fake_youtube_collect)
    collect = client.post(
        f"/api/v1/projects/{project['id']}/trends/collect", headers=auth_headers
    ).json()
    trend_id = collect["trends"][0]["id"]
    client.post(
        f"/api/v1/projects/{project['id']}/trends/{trend_id}/select",
        headers=auth_headers,
    )

    accepted = client.post(
        "/api/v1/content/generate",
        json={"trend_id": trend_id, "format": "short", "async_mode": True},
        headers=auth_headers,
    )
    assert accepted.status_code == 202
    body = accepted.json()
    assert body["job_id"]
    assert body["content_id"]
    assert body["status"] == "queued"

    job = client.get(
        f"/api/v1/content/jobs/{body['job_id']}", headers=auth_headers
    )
    assert job.status_code == 200
    assert job.json()["job_id"] == body["job_id"]

    content = client.get(
        f"/api/v1/content/{body['content_id']}", headers=auth_headers
    ).json()
    assert content["format"] == "short"
    assert content["status"] in {"PENDING", "GENERATED", "FAILED"}
