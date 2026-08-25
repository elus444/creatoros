"""In-app YouTube publish — uploads the real video via the connected channel."""

from fastapi.testclient import TestClient
import pytest
from fastapi import HTTPException, status

from app.models.user import User
from app.services.youtube_service import YouTubeService
from tests.test_content_workspace import _create_generated_content
from tests.test_youtube_oauth import _enable_oauth


def _approve(client: TestClient, headers: dict[str, str], content_id: str) -> None:
    review = client.post(f"/api/v1/content/{content_id}/review", headers=headers)
    assert review.status_code == 200
    approve = client.post(f"/api/v1/content/{content_id}/approve", headers=headers)
    assert approve.status_code == 200


def _connect_channel(client: TestClient) -> None:
    db = client.session_local()
    try:
        user = db.query(User).one()
        YouTubeService(db).store_tokens_for_tests(
            user,
            access_token="ya29.access-secret",
            refresh_token="1//refresh-secret",
            channel_id="UCabc",
            channel_title="Kids Counting Club",
        )
    finally:
        db.close()


def test_publish_uploads_approved_short(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_oauth(monkeypatch)
    created = _create_generated_content(client, auth_headers, monkeypatch)
    content_id = created["id"]
    _approve(client, auth_headers, content_id)
    _connect_channel(client)

    captured: dict = {}

    def fake_load(self, content) -> bytes:
        return b"fake-mp4-bytes"

    def fake_upload(self, *, access_token: str, metadata: dict, video_bytes: bytes) -> str:
        captured["access_token"] = access_token
        captured["metadata"] = metadata
        captured["video_bytes"] = video_bytes
        return "abcSHORTS1"

    monkeypatch.setattr(YouTubeService, "_load_video_bytes", fake_load)
    monkeypatch.setattr(YouTubeService, "_upload_video_to_youtube", fake_upload)
    monkeypatch.setattr(
        YouTubeService,
        "fetch_video_statistics",
        lambda self, user, ids: {
            ids[0]: {"views": 0, "likes": 0, "comments": 0},
        },
    )

    published = client.post(f"/api/v1/content/{content_id}/publish", headers=auth_headers)
    assert published.status_code == 200
    body = published.json()
    assert body["publish_status"] == "published"
    assert body["youtube_video_id"] == "abcSHORTS1"
    assert "access_token" not in body
    assert "ya29" not in str(body)
    assert captured["access_token"] == "ya29.access-secret"
    assert captured["video_bytes"] == b"fake-mp4-bytes"
    snippet = captured["metadata"]["snippet"]
    assert snippet["title"]
    assert "#Shorts" in snippet["description"]
    assert captured["metadata"]["status"]["privacyStatus"] == "public"

    db = client.session_local()
    try:
        from app.models.analytics_daily import AnalyticsDaily
        from uuid import UUID

        row = db.query(AnalyticsDaily).filter(
            AnalyticsDaily.content_id == UUID(content_id)
        ).one()
        assert row.views == 0
        assert row.likes == 0
        assert row.comments == 0
    finally:
        db.close()

    summary = client.get(
        f"/api/v1/analytics/projects/{created['project_id']}?range_days=7",
        headers=auth_headers,
    )
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["has_data"] is True
    assert payload["published_count"] == 1
    assert payload["top_content"][0]["content_id"] == content_id

    again = client.post(f"/api/v1/content/{content_id}/publish", headers=auth_headers)
    assert again.status_code == 200
    assert again.json()["youtube_video_id"] == "abcSHORTS1"


def test_publish_rejects_concurrent_claim_while_uploading(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two near-simultaneous publish calls must not both start an upload.

    Simulates the race directly against the service's atomic claim: once
    one caller has claimed the row (moved it to UPLOADING), a second call
    for the same content must be rejected with 409 rather than silently
    re-uploading — regression test for the check-and-set race fix.
    """
    _enable_oauth(monkeypatch)
    created = _create_generated_content(client, auth_headers, monkeypatch)
    content_id = created["id"]
    _approve(client, auth_headers, content_id)
    _connect_channel(client)

    from uuid import UUID

    from app.models.content import Content

    db = client.session_local()
    try:
        service = YouTubeService(db)
        content = db.get(Content, UUID(content_id))

        # First caller claims the row for upload.
        claimed = service._claim_for_publish(content)
        assert claimed is True
        assert content.publish_status == "uploading"

        # A second, concurrent caller loading the same row must be turned
        # away rather than claiming it a second time.
        content_again = db.get(Content, UUID(content_id))
        with pytest.raises(HTTPException) as exc_info:
            service._claim_for_publish(content_again)
        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    finally:
        db.close()


def test_publish_requires_connected_channel(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _create_generated_content(client, auth_headers, monkeypatch)
    content_id = created["id"]
    _approve(client, auth_headers, content_id)

    response = client.post(f"/api/v1/content/{content_id}/publish", headers=auth_headers)
    assert response.status_code == 400
    assert "connect youtube" in response.json()["detail"].lower()


def test_publish_rejects_unapproved_video(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _create_generated_content(client, auth_headers, monkeypatch)
    response = client.post(
        f"/api/v1/content/{created['id']}/publish", headers=auth_headers
    )
    assert response.status_code == 409


def test_publish_marks_failed_when_youtube_rejects(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_oauth(monkeypatch)
    created = _create_generated_content(client, auth_headers, monkeypatch)
    content_id = created["id"]
    _approve(client, auth_headers, content_id)
    _connect_channel(client)

    monkeypatch.setattr(YouTubeService, "_load_video_bytes", lambda self, content: b"bytes")

    def boom(self, **kwargs):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="YouTube rejected the video upload.",
        )

    monkeypatch.setattr(YouTubeService, "_upload_video_to_youtube", boom)

    response = client.post(f"/api/v1/content/{content_id}/publish", headers=auth_headers)
    assert response.status_code == 502

    status_body = client.get(f"/api/v1/content/{content_id}", headers=auth_headers).json()
    assert status_body["publish_status"] == "failed"
    assert status_body["youtube_video_id"] is None
    assert status_body["status"] == "APPROVED"
