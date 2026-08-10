from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.services.collectors import CollectedItem
from app.services.collectors.google_trends_collector import GoogleTrendsCollector
from app.services.collectors.youtube_collector import YouTubeCollector


def _create_project(client: TestClient, headers: dict[str, str], **overrides) -> str:
    payload = {"name": "Cooking Channel", "niche": "quick recipes"}
    payload.update(overrides)
    response = client.post("/api/v1/projects", json=payload, headers=headers)
    assert response.status_code == 201
    return response.json()["id"]


def test_collect_trends_persists_and_scores(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = _create_project(client, auth_headers)

    async def fake_youtube_collect(self, query, limit=10):
        assert query == "quick recipes"
        return [
            CollectedItem(
                title="5-minute pasta trend",
                source="youtube",
                url="https://www.youtube.com/watch?v=abc123",
                published_at=datetime.now(tz=UTC),
                metrics={"views": 120_000, "likes": 8_000, "comments": 300},
            )
        ]

    monkeypatch.setattr(YouTubeCollector, "collect", fake_youtube_collect)

    response = client.post(
        f"/api/v1/projects/{project_id}/trends/collect", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["collected"] == 1
    assert data["sources_used"] == ["google_trends", "youtube"]
    assert data["warnings"] == []
    assert len(data["trends"]) == 1
    trend = data["trends"][0]
    assert trend["title"] == "5-minute pasta trend"
    assert trend["score"] > 0

    list_response = client.get(
        f"/api/v1/projects/{project_id}/trends", headers=auth_headers
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_collect_trends_includes_google_trends_source(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = _create_project(client, auth_headers)

    async def fake_google_collect(self, query, limit=10):
        assert query == "quick recipes"
        return [
            CollectedItem(
                title="quick recipes trending now",
                source="google_trends",
                url="https://trends.google.com/trends/explore?q=quick+recipes",
                published_at=datetime.now(tz=UTC),
                metrics={
                    "approx_traffic": "5K+",
                    "approx_traffic_numeric": 5000,
                    "related_articles": 2,
                },
            )
        ]

    async def fake_youtube_collect(self, query, limit=10):
        return []

    monkeypatch.setattr(GoogleTrendsCollector, "collect", fake_google_collect)
    monkeypatch.setattr(YouTubeCollector, "collect", fake_youtube_collect)

    response = client.post(
        f"/api/v1/projects/{project_id}/trends/collect", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["collected"] == 1
    assert data["sources_used"] == ["google_trends", "youtube"]
    trend = data["trends"][0]
    assert trend["source"] == "google_trends"
    assert trend["score"] > 0


def test_collect_trends_dedupes_by_url(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = _create_project(client, auth_headers)

    async def fake_youtube_collect(self, query, limit=10):
        return [
            CollectedItem(
                title="Same video",
                source="youtube",
                url="https://www.youtube.com/watch?v=same",
                published_at=datetime.now(tz=UTC),
                metrics={"views": 100, "likes": 5, "comments": 1},
            )
        ]

    monkeypatch.setattr(YouTubeCollector, "collect", fake_youtube_collect)

    first = client.post(
        f"/api/v1/projects/{project_id}/trends/collect", headers=auth_headers
    )
    assert first.json()["collected"] == 1

    second = client.post(
        f"/api/v1/projects/{project_id}/trends/collect", headers=auth_headers
    )
    assert second.json()["collected"] == 0
    assert len(second.json()["trends"]) == 1


def test_select_trend_uses_single_selection_semantics(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = _create_project(client, auth_headers)

    async def fake_youtube_collect(self, query, limit=10):
        return [
            CollectedItem(
                title="Trend A",
                source="youtube",
                url="https://www.youtube.com/watch?v=a",
                published_at=datetime.now(tz=UTC),
                metrics={"views": 10_000, "likes": 500, "comments": 40},
            ),
            CollectedItem(
                title="Trend B",
                source="youtube",
                url="https://www.youtube.com/watch?v=b",
                published_at=datetime.now(tz=UTC),
                metrics={"views": 5_000, "likes": 200, "comments": 20},
            ),
        ]

    monkeypatch.setattr(YouTubeCollector, "collect", fake_youtube_collect)

    collect_response = client.post(
        f"/api/v1/projects/{project_id}/trends/collect", headers=auth_headers
    )
    trends = collect_response.json()["trends"]
    assert len(trends) == 2

    select_first = client.post(
        f"/api/v1/projects/{project_id}/trends/{trends[0]['id']}/select",
        headers=auth_headers,
    )
    assert select_first.status_code == 200
    assert select_first.json()["is_selected"] is True

    select_second = client.post(
        f"/api/v1/projects/{project_id}/trends/{trends[1]['id']}/select",
        headers=auth_headers,
    )
    assert select_second.json()["is_selected"] is True

    list_response = client.get(
        f"/api/v1/projects/{project_id}/trends", headers=auth_headers
    )
    selected = [t for t in list_response.json() if t["is_selected"]]
    assert len(selected) == 1
    assert selected[0]["id"] == trends[1]["id"]


def test_trends_require_ownership(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    project_id = _create_project(client, auth_headers)
    intruder_token = client.post(
        "/api/v1/auth/register",
        json={"email": "intruder2@example.com", "password": "securepass1"},
    ).json()["access_token"]

    response = client.get(
        f"/api/v1/projects/{project_id}/trends",
        headers={"Authorization": f"Bearer {intruder_token}"},
    )
    assert response.status_code == 404


def test_collect_reports_warning_when_youtube_not_configured(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "youtube_api_key", None)

    project_id = _create_project(client, auth_headers)
    response = client.post(
        f"/api/v1/projects/{project_id}/trends/collect", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["collected"] == 0
    assert data["sources_used"] == ["google_trends"]
    assert len(data["warnings"]) == 1
    assert "YouTube" in data["warnings"][0]


def test_collect_fails_gracefully_when_collector_errors(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.collectors.base import CollectorError

    async def fake_youtube_collect(self, query, limit=10):
        raise CollectorError("YouTube API returned HTTP 429")

    monkeypatch.setattr(YouTubeCollector, "collect", fake_youtube_collect)

    project_id = _create_project(client, auth_headers)
    response = client.post(
        f"/api/v1/projects/{project_id}/trends/collect", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["collected"] == 0
    assert data["sources_used"] == ["google_trends"]
    assert len(data["warnings"]) == 1
