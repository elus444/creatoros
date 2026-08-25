"""M6 analytics ingest, aggregation, ownership, and Coach insufficient-data."""

from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.schemas.agent_outputs import AnalyticsAgentOutput, CoachAgentOutput
from app.services.llm_service import LLMResult, LLMService


def _create_project(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/projects",
        json={
            "name": "Analytics Project",
            "niche": "youtube shorts tips",
            "audience": "creators",
            "brand_voice": "clear and practical",
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


def _seed_content(
    client: TestClient, headers: dict[str, str], project_id: str, title: str
) -> str:
    """Insert content + trend directly so tests don't depend on collectors/LLM."""
    from app.models.content import Content, ContentStatus
    from app.models.trend import Trend
    from uuid import UUID

    db = client.session_local()
    try:
        trend = Trend(
            project_id=UUID(project_id),
            title=f"Trend for {title}",
            source="youtube",
            url=f"https://example.com/trends/{uuid4()}",
            score=80.0,
            metrics={"views": 1000},
            is_selected=True,
        )
        db.add(trend)
        db.flush()
        content = Content(
            project_id=UUID(project_id),
            trend_id=trend.id,
            research={"summary": "r", "facts": ["f"], "audience_insights": ["a"], "opportunities": ["o"]},
            strategy={
                "angle": f"Angle {title}",
                "hooks": [f"Hook {title}"],
                "target_audience": "creators",
                "structure": ["hook", "body"],
            },
            script=f"Script for {title}",
            titles=[title],
            captions=f"Caption {title}",
            hashtags=["analytics"],
            status=ContentStatus.APPROVED,
        )
        db.add(content)
        db.commit()
        return str(content.id)
    finally:
        db.close()


def _ingest(
    client: TestClient,
    headers: dict[str, str],
    content_id: str,
    *,
    views: int,
    likes: int,
    comments: int,
    day: date | None = None,
):
    return client.post(
        "/api/v1/analytics/ingest",
        headers=headers,
        json={
            "content_id": content_id,
            "views": views,
            "likes": likes,
            "comments": comments,
            "date": (day or date.today()).isoformat(),
        },
    )


def test_ingest_rejects_negative_metrics(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    project_id = _create_project(client, auth_headers)
    content_id = _seed_content(client, auth_headers, project_id, "Neg Title")
    response = client.post(
        "/api/v1/analytics/ingest",
        headers=auth_headers,
        json={
            "content_id": content_id,
            "views": -1,
            "likes": 0,
            "comments": 0,
            "date": date.today().isoformat(),
        },
    )
    assert response.status_code == 422


def test_ingest_rejects_unknown_content(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/analytics/ingest",
        headers=auth_headers,
        json={
            "content_id": str(uuid4()),
            "views": 10,
            "likes": 1,
            "comments": 0,
            "date": date.today().isoformat(),
        },
    )
    assert response.status_code == 404


def test_ingest_calculates_engagement_server_side(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    project_id = _create_project(client, auth_headers)
    content_id = _seed_content(client, auth_headers, project_id, "Engage Title")
    response = _ingest(
        client, auth_headers, content_id, views=100, likes=10, comments=5
    )
    assert response.status_code == 201
    body = response.json()
    # (10+5)/100 * 100 = 15
    assert body["engagement_rate"] == pytest.approx(15.0)
    assert body["views"] == 100


def test_ingest_upserts_same_day(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    project_id = _create_project(client, auth_headers)
    content_id = _seed_content(client, auth_headers, project_id, "Upsert Title")
    day = date.today().isoformat()
    first = client.post(
        "/api/v1/analytics/ingest",
        headers=auth_headers,
        json={
            "content_id": content_id,
            "views": 50,
            "likes": 2,
            "comments": 1,
            "date": day,
        },
    )
    second = client.post(
        "/api/v1/analytics/ingest",
        headers=auth_headers,
        json={
            "content_id": content_id,
            "views": 80,
            "likes": 4,
            "comments": 2,
            "date": day,
        },
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["views"] == 80

    summary = client.get(
        f"/api/v1/analytics/content/{content_id}?range_days=30",
        headers=auth_headers,
    )
    assert summary.status_code == 200
    assert summary.json()["totals"]["daily_rows"] == 1
    assert summary.json()["totals"]["views"] == 80


def test_project_summary_and_top_content(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    project_id = _create_project(client, auth_headers)
    c1 = _seed_content(client, auth_headers, project_id, "Winner")
    c2 = _seed_content(client, auth_headers, project_id, "Runner")
    assert _ingest(client, auth_headers, c1, views=500, likes=40, comments=10).status_code == 201
    assert _ingest(client, auth_headers, c2, views=100, likes=5, comments=1).status_code == 201
    # Older day for series
    older = date.today() - timedelta(days=2)
    assert (
        _ingest(
            client, auth_headers, c1, views=200, likes=10, comments=2, day=older
        ).status_code
        == 201
    )

    summary = client.get(
        f"/api/v1/analytics/projects/{project_id}?range_days=30",
        headers=auth_headers,
    )
    assert summary.status_code == 200
    body = summary.json()
    assert body["has_data"] is True
    assert body["totals"]["views"] == 800
    assert body["totals"]["content_with_metrics"] == 2
    assert len(body["series"]) >= 2
    assert body["top_content"][0]["title"] == "Winner"
    assert body["top_content"][0]["views"] == 700


def test_analytics_ownership_isolation(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    project_id = _create_project(client, auth_headers)
    content_id = _seed_content(client, auth_headers, project_id, "Private")
    assert _ingest(client, auth_headers, content_id, views=10, likes=1, comments=0).status_code == 201

    other = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"other_{uuid4().hex[:8]}@example.com",
            "password": "SecurePass123!",
            "full_name": "Other User",
        },
    )
    assert other.status_code == 201
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}

    assert (
        client.get(
            f"/api/v1/analytics/projects/{project_id}", headers=other_headers
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/analytics/content/{content_id}", headers=other_headers
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/analytics/ingest",
            headers=other_headers,
            json={
                "content_id": content_id,
                "views": 999,
                "likes": 9,
                "comments": 9,
                "date": date.today().isoformat(),
            },
        ).status_code
        == 404
    )


def test_empty_analytics(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    project_id = _create_project(client, auth_headers)
    summary = client.get(
        f"/api/v1/analytics/projects/{project_id}?range_days=7",
        headers=auth_headers,
    )
    assert summary.status_code == 200
    body = summary.json()
    assert body["has_data"] is False
    assert body["totals"]["views"] == 0
    assert body["top_content"] == []
    assert body["published_count"] == 0


def test_coach_insufficient_data(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    project_id = _create_project(client, auth_headers)
    c1 = _seed_content(client, auth_headers, project_id, "Only One")
    assert _ingest(client, auth_headers, c1, views=50, likes=2, comments=1).status_code == 201

    response = client.post(
        f"/api/v1/analytics/projects/{project_id}/coach",
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "insufficient_data"
    assert body["recommendations"] == []
    assert "Not enough performance data" in body["message"]


def _llm_result(data: dict) -> LLMResult:
    return LLMResult(
        data=data,
        raw_text=str(data),
        model="test",
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
    )


def test_coach_ready_with_enough_data(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analytics_out = {
        "top_patterns": ["Curiosity hooks drive views"],
        "weak_patterns": ["Generic titles underperform"],
        "observations": ["Top piece has 500 views with 10% engagement"],
        "confidence": "medium",
    }
    coach_out = {
        "recommendations": [
            {
                "title": "Use stronger curiosity hooks",
                "reason": "Highest-viewed posts use curiosity openings.",
                "action": "Test 3 scripts with curiosity hooks this week.",
                "priority": "high",
            },
            {
                "title": "Avoid generic titles",
                "reason": "Lower performers used vague titles.",
                "action": "Rewrite next 2 titles with a specific promise.",
                "priority": "medium",
            },
            {
                "title": "Double down on winning topic",
                "reason": "Top content clustered around one niche angle.",
                "action": "Ship one follow-up on the same angle.",
                "priority": "high",
            },
        ],
        "summary": "Lean into curiosity hooks and sharper titles.",
    }

    script = {
        AnalyticsAgentOutput: [_llm_result(analytics_out)],
        CoachAgentOutput: [_llm_result(coach_out)],
    }

    async def fake_generate_structured(
        self, *, prompt, response_model, system_instruction=None, temperature=0.4
    ):
        items = script.get(response_model)
        if not items:
            raise AssertionError(f"No scripted response for {response_model}")
        return items.pop(0)

    monkeypatch.setattr(LLMService, "generate_structured", fake_generate_structured)

    project_id = _create_project(client, auth_headers)
    ids = [
        _seed_content(client, auth_headers, project_id, f"Piece {i}")
        for i in range(3)
    ]
    for i, cid in enumerate(ids):
        assert (
            _ingest(
                client,
                auth_headers,
                cid,
                views=100 * (i + 1),
                likes=10 * (i + 1),
                comments=i + 1,
            ).status_code
            == 201
        )

    response = client.post(
        f"/api/v1/analytics/projects/{project_id}/coach",
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert len(body["recommendations"]) >= 3
    assert body["confidence"] == "medium"
    assert body["analytics"]["top_patterns"]

    # Agent runs logged with project_id
    from app.models.agent_run import AgentRun

    db = client.session_local()
    try:
        runs = db.query(AgentRun).filter(AgentRun.project_id.isnot(None)).all()
        names = {r.agent_name for r in runs}
        assert "analytics" in names
        assert "coach" in names
    finally:
        db.close()


def test_invalid_range_days(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    project_id = _create_project(client, auth_headers)
    response = client.get(
        f"/api/v1/analytics/projects/{project_id}?range_days=14",
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_sync_from_youtube_stores_live_statistics(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from uuid import UUID

    from app.models.content import Content, PublishStatus
    from app.services.youtube_service import YouTubeService

    project_id = _create_project(client, auth_headers)
    content_id = _seed_content(client, auth_headers, project_id, "Published Short")
    db = client.session_local()
    try:
        row = db.get(Content, UUID(content_id))
        row.publish_status = PublishStatus.PUBLISHED
        row.youtube_video_id = "ytVid123"
        db.commit()
    finally:
        db.close()

    def fake_fetch(self, user, ids):
        assert ids == ["ytVid123"]
        return {"ytVid123": {"views": 42, "likes": 3, "comments": 1}}

    monkeypatch.setattr(YouTubeService, "fetch_video_statistics", fake_fetch)

    synced = client.post(
        f"/api/v1/analytics/projects/{project_id}/sync",
        headers=auth_headers,
    )
    assert synced.status_code == 200
    body = synced.json()
    assert body["synced"] == 1
    assert body["published"] == 1
    assert "42" not in str(body)

    summary = client.get(
        f"/api/v1/analytics/projects/{project_id}?range_days=7",
        headers=auth_headers,
    )
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["has_data"] is True
    assert payload["published_count"] == 1
    assert payload["totals"]["views"] == 42
    assert payload["totals"]["likes"] == 3
    assert payload["totals"]["comments"] == 1
    assert payload["top_content"][0]["content_id"] == content_id


def test_sync_does_not_invent_stats_when_youtube_omits_video(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from uuid import UUID

    from app.models.content import Content, PublishStatus
    from app.services.youtube_service import YouTubeService

    project_id = _create_project(client, auth_headers)
    content_id = _seed_content(client, auth_headers, project_id, "Processing Short")
    db = client.session_local()
    try:
        row = db.get(Content, UUID(content_id))
        row.publish_status = PublishStatus.PUBLISHED
        row.youtube_video_id = "missingVid"
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(
        YouTubeService, "fetch_video_statistics", lambda self, user, ids: {}
    )
    synced = client.post(
        f"/api/v1/analytics/projects/{project_id}/sync",
        headers=auth_headers,
    )
    assert synced.status_code == 200
    assert synced.json()["synced"] == 0

    summary = client.get(
        f"/api/v1/analytics/projects/{project_id}?range_days=7",
        headers=auth_headers,
    )
    assert summary.json()["has_data"] is False
    assert summary.json()["published_count"] == 0
    assert summary.json()["totals"]["views"] == 0
    assert summary.json()["top_content"] == []


def test_sync_clears_stale_report_when_youtube_video_is_gone(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from uuid import UUID

    from app.models.content import Content, PublishStatus
    from app.services.youtube_service import YouTubeService

    project_id = _create_project(client, auth_headers)
    content_id = _seed_content(client, auth_headers, project_id, "Deleted Short")
    db = client.session_local()
    try:
        row = db.get(Content, UUID(content_id))
        row.publish_status = PublishStatus.PUBLISHED
        row.youtube_video_id = "deletedVid"
        db.commit()
    finally:
        db.close()

    live = {"gone": False}

    def fake_fetch(self, user, ids):
        if live["gone"]:
            return {}
        return {"deletedVid": {"views": 120, "likes": 8, "comments": 2}}

    monkeypatch.setattr(YouTubeService, "fetch_video_statistics", fake_fetch)

    before = client.get(
        f"/api/v1/analytics/projects/{project_id}?range_days=7",
        headers=auth_headers,
    )
    assert before.json()["has_data"] is True
    assert before.json()["totals"]["views"] == 120
    assert before.json()["top_content"]

    live["gone"] = True
    synced = client.post(
        f"/api/v1/analytics/projects/{project_id}/sync",
        headers=auth_headers,
    )
    assert synced.status_code == 200
    assert synced.json()["cleared"] >= 1
    assert synced.json()["synced"] == 0

    after = client.get(
        f"/api/v1/analytics/projects/{project_id}?range_days=7",
        headers=auth_headers,
    )
    assert after.json()["has_data"] is False
    assert after.json()["published_count"] == 0
    assert after.json()["totals"]["views"] == 0
    assert after.json()["top_content"] == []
