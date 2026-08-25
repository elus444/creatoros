from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

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

    async def fake_google_collect(self, query, limit=10, **kwargs):
        return []

    async def fake_youtube_collect(self, query, limit=10, **kwargs):
        assert query == "quick recipes"
        return [
            CollectedItem(
                title="5-minute pasta trend",
                source="youtube",
                url="https://www.youtube.com/shorts/abc123",
                published_at=datetime.now(tz=UTC),
                metrics={"views": 120_000, "likes": 8_000, "comments": 300},
                default_language="en",
                default_audio_language="en-US",
            )
        ]

    monkeypatch.setattr(GoogleTrendsCollector, "collect", fake_google_collect)
    monkeypatch.setattr(YouTubeCollector, "collect", fake_youtube_collect)

    response = client.post(
        f"/api/v1/projects/{project_id}/trends/collect", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["collected"] == 1
    assert data["sources_used"] == ["youtube"]
    assert any(w.startswith("Kept ") for w in data["warnings"])
    assert not any("failed" in w.lower() for w in data["warnings"])
    assert len(data["trends"]) == 1
    trend = data["trends"][0]
    assert trend["title"] == "5-minute pasta trend"
    assert trend["score"] > 0
    assert trend["language"] == "en"

    list_response = client.get(
        f"/api/v1/projects/{project_id}/trends", headers=auth_headers
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_collect_keeps_english_shorts_without_audio_tags(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = _create_project(client, auth_headers)

    async def fake_youtube_collect(self, query, limit=10, **kwargs):
        return [
            CollectedItem(
                title="How to make kids counting Shorts",
                source="youtube",
                url="https://www.youtube.com/shorts/notag1",
                published_at=datetime.now(tz=UTC),
                metrics={"views": 12_000, "likes": 400, "comments": 20},
            )
        ]

    monkeypatch.setattr(YouTubeCollector, "collect", fake_youtube_collect)
    first = client.post(
        f"/api/v1/projects/{project_id}/trends/collect", headers=auth_headers
    )
    assert first.status_code == 200
    assert first.json()["collected"] == 1

    async def fake_youtube_collect_second(self, query, limit=10, **kwargs):
        return [
            CollectedItem(
                title="Easy pasta dinner ideas for busy nights",
                source="youtube",
                url="https://www.youtube.com/shorts/notag2",
                published_at=datetime.now(tz=UTC),
                metrics={"views": 9_000, "likes": 300, "comments": 15},
            )
        ]

    monkeypatch.setattr(YouTubeCollector, "collect", fake_youtube_collect_second)
    second = client.post(
        f"/api/v1/projects/{project_id}/trends/collect", headers=auth_headers
    )
    assert second.json()["collected"] == 1
    titles = {t["title"] for t in second.json()["trends"]}
    assert "Easy pasta dinner ideas for busy nights" in titles


def test_collect_does_not_call_google_trends(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = _create_project(client, auth_headers)
    called = {"google": False}

    async def fake_google_collect(self, query, limit=10, **kwargs):
        called["google"] = True
        return []

    async def fake_youtube_collect(self, query, limit=10, **kwargs):
        return [
            CollectedItem(
                title="Kids counting Short",
                source="youtube",
                url="https://www.youtube.com/shorts/short1",
                published_at=datetime.now(tz=UTC),
                metrics={"views": 10_000, "likes": 800, "comments": 40},
                default_audio_language="en",
            )
        ]

    monkeypatch.setattr(GoogleTrendsCollector, "collect", fake_google_collect)
    monkeypatch.setattr(YouTubeCollector, "collect", fake_youtube_collect)

    response = client.post(
        f"/api/v1/projects/{project_id}/trends/collect", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert called["google"] is False
    assert data["sources_used"] == ["youtube"]
    assert data["trends"][0]["url"].startswith("https://www.youtube.com/shorts/")


def test_collect_trends_dedupes_by_url(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = _create_project(client, auth_headers)

    async def fake_google_collect(self, query, limit=10, **kwargs):
        return []

    async def fake_youtube_collect(self, query, limit=10, **kwargs):
        return [
            CollectedItem(
                title="Same video editing tip",
                source="youtube",
                url="https://www.youtube.com/shorts/same",
                published_at=datetime.now(tz=UTC),
                metrics={"views": 100, "likes": 5, "comments": 1},
                default_audio_language="en",
            )
        ]

    monkeypatch.setattr(GoogleTrendsCollector, "collect", fake_google_collect)
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


def test_collect_filters_non_english_and_similar_topics(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = _create_project(client, auth_headers)

    async def fake_google_collect(self, query, limit=10, **kwargs):
        return []

    async def fake_youtube_collect(self, query, limit=10, **kwargs):
        return [
            CollectedItem(
                title="Cómo cocinar pasta rápida hoy",
                source="youtube",
                url="https://www.youtube.com/shorts/es1",
                published_at=datetime.now(tz=UTC),
                metrics={"views": 200_000, "likes": 9_000, "comments": 400},
                description="English description about pasta cooking tips",
                default_audio_language="es-419",
            ),
            CollectedItem(
                title="Air fryer chicken tenders in 10 minutes",
                source="youtube",
                url="https://www.youtube.com/shorts/en1",
                published_at=datetime.now(tz=UTC),
                metrics={"views": 80_000, "likes": 6_000, "comments": 250},
                default_audio_language="en",
            ),
            CollectedItem(
                title="Air fryer chicken tenders quick recipe",
                source="youtube",
                url="https://www.youtube.com/shorts/en2",
                published_at=datetime.now(tz=UTC),
                metrics={"views": 70_000, "likes": 5_000, "comments": 200},
                default_audio_language="en",
            ),
            CollectedItem(
                title="Meal prep rice bowls for busy weeks",
                source="youtube",
                url="https://www.youtube.com/shorts/en3",
                published_at=datetime.now(tz=UTC),
                metrics={"views": 40_000, "likes": 3_000, "comments": 120},
                default_audio_language="en",
            ),
        ]

    monkeypatch.setattr(GoogleTrendsCollector, "collect", fake_google_collect)
    monkeypatch.setattr(YouTubeCollector, "collect", fake_youtube_collect)

    first = client.post(
        f"/api/v1/projects/{project_id}/trends/collect", headers=auth_headers
    )
    assert first.status_code == 200
    data = first.json()
    assert data["collected"] == 2
    titles = {t["title"] for t in data["trends"]}
    assert "Cómo cocinar pasta rápida hoy" not in titles
    assert "Air fryer chicken tenders in 10 minutes" in titles
    assert "Meal prep rice bowls for busy weeks" in titles
    assert "Air fryer chicken tenders quick recipe" not in titles
    scores = [t["score"] for t in data["trends"]]
    assert len(set(scores)) == len(scores)
    assert any("not spoken English" in w for w in data["warnings"])

    async def fake_youtube_collect_second(self, query, limit=10, **kwargs):
        return [
            CollectedItem(
                title="Air fryer chicken tenders crispy style",
                source="youtube",
                url="https://www.youtube.com/shorts/en4",
                published_at=datetime.now(tz=UTC),
                metrics={"views": 90_000, "likes": 7_000, "comments": 300},
                default_audio_language="en",
            ),
            CollectedItem(
                title="Overnight oats breakfast trend",
                source="youtube",
                url="https://www.youtube.com/shorts/en5",
                published_at=datetime.now(tz=UTC),
                metrics={"views": 55_000, "likes": 4_000, "comments": 180},
                default_audio_language="en",
            ),
        ]

    monkeypatch.setattr(YouTubeCollector, "collect", fake_youtube_collect_second)
    second = client.post(
        f"/api/v1/projects/{project_id}/trends/collect", headers=auth_headers
    )
    assert second.json()["collected"] == 1
    second_titles = {t["title"] for t in second.json()["trends"]}
    assert "Overnight oats breakfast trend" in second_titles
    assert "Air fryer chicken tenders crispy style" not in second_titles


def test_select_trend_uses_single_selection_semantics(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = _create_project(client, auth_headers)

    async def fake_google_collect(self, query, limit=10, **kwargs):
        return []

    async def fake_youtube_collect(self, query, limit=10, **kwargs):
        return [
            CollectedItem(
                title="Trend A pasta hacks",
                source="youtube",
                url="https://www.youtube.com/shorts/a",
                published_at=datetime.now(tz=UTC),
                metrics={"views": 10_000, "likes": 500, "comments": 40},
                default_audio_language="en",
            ),
            CollectedItem(
                title="Trend B meal prep bowls",
                source="youtube",
                url="https://www.youtube.com/shorts/b",
                published_at=datetime.now(tz=UTC),
                metrics={"views": 5_000, "likes": 200, "comments": 20},
                default_audio_language="en",
            ),
        ]

    monkeypatch.setattr(GoogleTrendsCollector, "collect", fake_google_collect)
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

    async def fake_google_collect(self, query, limit=10, **kwargs):
        return []

    monkeypatch.setattr(get_settings(), "youtube_api_key", None)
    monkeypatch.setattr(GoogleTrendsCollector, "collect", fake_google_collect)

    project_id = _create_project(client, auth_headers)
    response = client.post(
        f"/api/v1/projects/{project_id}/trends/collect", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["collected"] == 0
    assert data["sources_used"] == []
    assert any("YouTube" in w for w in data["warnings"])


def test_collect_fails_gracefully_when_collector_errors(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.collectors.base import CollectorError

    async def fake_google_collect(self, query, limit=10, **kwargs):
        return []

    async def fake_youtube_collect(self, query, limit=10, **kwargs):
        raise CollectorError("YouTube API returned HTTP 429")

    monkeypatch.setattr(GoogleTrendsCollector, "collect", fake_google_collect)
    monkeypatch.setattr(YouTubeCollector, "collect", fake_youtube_collect)

    project_id = _create_project(client, auth_headers)
    response = client.post(
        f"/api/v1/projects/{project_id}/trends/collect", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["collected"] == 0
    assert data["sources_used"] == []
    assert any("collection failed" in w for w in data["warnings"])


def test_collect_fails_gracefully_when_collector_raises_unexpected_error(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_google_collect(self, query, limit=10, **kwargs):
        return []

    async def fake_youtube_collect(self, query, limit=10, **kwargs):
        raise ValueError("malformed provider field")

    monkeypatch.setattr(GoogleTrendsCollector, "collect", fake_google_collect)
    monkeypatch.setattr(YouTubeCollector, "collect", fake_youtube_collect)
    project_id = _create_project(client, auth_headers)

    response = client.post(
        f"/api/v1/projects/{project_id}/trends/collect", headers=auth_headers
    )

    assert response.status_code == 200
    assert "youtube collection failed unexpectedly." in response.json()["warnings"]


def test_trend_database_constraint_rejects_duplicate_project_url(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    from app.models.trend import Trend

    project_id = _create_project(client, auth_headers)
    db = client.session_local()
    try:
        db.add_all(
            [
                Trend(
                    project_id=UUID(project_id),
                    title="First",
                    source="youtube",
                    url="https://example.com/duplicate",
                    score=1,
                ),
                Trend(
                    project_id=UUID(project_id),
                    title="Second",
                    source="youtube",
                    url="https://example.com/duplicate",
                    score=1,
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.close()
