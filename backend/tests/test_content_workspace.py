"""M4 Content Workspace API tests — list, edit, status flow, regenerate,
suggest, export. LLM calls are faked at LLMService.generate_structured.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.schemas.agent_outputs import ResearchOutput, StrategyOutput, SuggestionOutput, VideoOutput
from app.services.collectors import CollectedItem
from app.services.collectors.youtube_collector import YouTubeCollector
from app.services.llm_service import LLMResult, LLMService
from tests.video_pipeline_fakes import GENERATE_BODY, install_fake_video_provider

VALID_RESEARCH = {
    "summary": "Quick recipes are trending among busy home cooks.",
    "facts": ["Search interest for 5-minute meals is up."],
    "audience_insights": ["Viewers want minimal cleanup."],
    "opportunities": ["A one-pan pasta series."],
}
VALID_STRATEGY = {
    "angle": "One-pan, 5-ingredient pasta recipes.",
    "hooks": ["You only need one pan for this."],
    "target_audience": "Busy home cooks who hate dishes.",
    "structure": ["hook", "ingredients", "steps", "payoff", "cta"],
}
VALID_VIDEO = {
    "concept": "One-pan pasta concept.",
    "scenes": ["hook", "cook", "payoff"],
    "visual_direction": "Bright kitchen.",
    "narration": "Narration for the video.",
    "titles": ["One Pan Pasta"],
    "caption": "Easy pasta caption",
    "hashtags": ["pasta"],
    "aspect_ratio": "9:16",
    "duration_seconds": 10,
}
VALID_SUGGESTION = {
    "suggestions": ["Try this sharper opener instead.", "Lead with the dish reveal."],
    "rationale": "Stronger hooks win the first three seconds.",
}


def _llm_result(data: dict) -> LLMResult:
    return LLMResult(
        data=data,
        raw_text=str(data),
        model="gemini-flash-lite-latest",
        prompt_tokens=12,
        completion_tokens=34,
        total_tokens=46,
    )


def _install_fake_llm(monkeypatch: pytest.MonkeyPatch, script: dict[type, list]) -> None:
    async def fake_generate_structured(
        self, *, prompt, response_model, system_instruction=None, temperature=0.4
    ):
        items = script.get(response_model)
        if not items:
            raise AssertionError(f"No scripted response left for {response_model}")
        item = items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(LLMService, "generate_structured", fake_generate_structured)


def _create_generated_content(
    client: TestClient, headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> dict:
    install_fake_video_provider(monkeypatch)
    project = client.post(
        "/api/v1/projects",
        json={
            "name": "Cooking Channel",
            "niche": "quick recipes",
            "audience": "busy cooks",
            "brand_voice": "upbeat",
        },
        headers=headers,
    ).json()

    async def fake_youtube_collect(self, query, limit=10, **kwargs):
        return [
            CollectedItem(
                title="5-minute pasta trend",
                source="youtube",
                url="https://www.youtube.com/shorts/abc123",
                published_at=datetime.now(tz=UTC),
                metrics={"views": 120_000, "likes": 8_000, "comments": 300},
                default_audio_language="en",
            )
        ]

    monkeypatch.setattr(YouTubeCollector, "collect", fake_youtube_collect)
    collect = client.post(
        f"/api/v1/projects/{project['id']}/trends/collect", headers=headers
    ).json()
    trend_id = collect["trends"][0]["id"]
    client.post(
        f"/api/v1/projects/{project['id']}/trends/{trend_id}/select", headers=headers
    )

    _install_fake_llm(
        monkeypatch,
        {
            ResearchOutput: [_llm_result(VALID_RESEARCH)],
            StrategyOutput: [_llm_result(VALID_STRATEGY)],
            VideoOutput: [_llm_result(VALID_VIDEO)],
        },
    )
    response = client.post(
        "/api/v1/content/generate", json={"trend_id": trend_id, **GENERATE_BODY}, headers=headers
    )
    assert response.status_code == 201
    return response.json()


def test_list_content_library(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _create_generated_content(client, auth_headers, monkeypatch)
    response = client.get("/api/v1/content", headers=auth_headers)
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["id"] == created["id"]
    assert items[0]["project_name"] == "Cooking Channel"
    assert items[0]["trend_title"] == "5-minute pasta trend"


def test_update_editable_fields(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _create_generated_content(client, auth_headers, monkeypatch)
    response = client.patch(
        f"/api/v1/content/{created['id']}",
        json={
            "script": "Revised script for the pan pasta.",
            "titles": ["Revised Title"],
            "captions": "Revised caption",
            "hashtags": ["#pasta", "quickmeals"],
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["script"] == "Revised script for the pan pasta."
    assert body["titles"] == ["Revised Title"]
    assert body["captions"] == "Revised caption"
    assert body["hashtags"] == ["pasta", "quickmeals"]


def test_status_flow_generated_review_approve_export(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _create_generated_content(client, auth_headers, monkeypatch)
    content_id = created["id"]

    review = client.post(f"/api/v1/content/{content_id}/review", headers=auth_headers)
    assert review.status_code == 200
    assert review.json()["status"] == "REVIEW"

    # Cannot skip approve from REVIEW by exporting directly? Export requires APPROVED.
    bad_export = client.post(f"/api/v1/content/{content_id}/export", headers=auth_headers)
    assert bad_export.status_code == 409

    approve = client.post(f"/api/v1/content/{content_id}/approve", headers=auth_headers)
    assert approve.status_code == 200
    assert approve.json()["status"] == "APPROVED"

    # Locked after approve
    locked = client.patch(
        f"/api/v1/content/{content_id}",
        json={"script": "should fail"},
        headers=auth_headers,
    )
    assert locked.status_code == 409

    exported = client.post(f"/api/v1/content/{content_id}/export", headers=auth_headers)
    assert exported.status_code == 200
    body = exported.json()
    assert body["status"] == "EXPORTED"
    assert body["filename"].endswith(".md")
    assert "## Narration" in body["body"]
    assert "Video URL:" in body["body"]
    assert "Narration for the video" in body["body"]
    assert "Format: short" in body["body"]


def test_regenerate_rewrites_content_fields(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _create_generated_content(client, auth_headers, monkeypatch)
    _install_fake_llm(
        monkeypatch,
        {
            VideoOutput: [
                _llm_result(
                    {
                        "concept": "Regen concept",
                        "scenes": ["a", "b"],
                        "visual_direction": "v",
                        "narration": "Brand new regenerated script.",
                        "titles": ["Regen Title"],
                        "caption": "Regen caption",
                        "hashtags": ["regen"],
                        "aspect_ratio": "9:16",
                        "duration_seconds": 10,
                    }
                )
            ]
        },
    )
    response = client.post(
        f"/api/v1/content/{created['id']}/regenerate", headers=auth_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "GENERATED"
    assert body["script"] == "Brand new regenerated script."
    assert body["titles"] == ["Regen Title"]


def test_suggest_returns_alternatives(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _create_generated_content(client, auth_headers, monkeypatch)
    _install_fake_llm(
        monkeypatch, {SuggestionOutput: [_llm_result(VALID_SUGGESTION)]}
    )
    response = client.post(
        f"/api/v1/content/{created['id']}/suggest",
        json={"target": "script", "guidance": "Make it punchier"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["target"] == "script"
    assert len(body["suggestions"]) == 2
    assert "hooks" in body["rationale"].lower() or body["rationale"]


def test_invalid_status_transition(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _create_generated_content(client, auth_headers, monkeypatch)
    # APPROVED requires REVIEW first
    response = client.post(
        f"/api/v1/content/{created['id']}/approve", headers=auth_headers
    )
    assert response.status_code == 409


def test_workspace_requires_ownership(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _create_generated_content(client, auth_headers, monkeypatch)
    intruder = client.post(
        "/api/v1/auth/register",
        json={"email": "m4-intruder@example.com", "password": "securepass1"},
    ).json()["access_token"]
    response = client.get(
        f"/api/v1/content/{created['id']}",
        headers={"Authorization": f"Bearer {intruder}"},
    )
    assert response.status_code == 404
    # Ensure UUID path still typed correctly for list filter ownership
    filtered = client.get(
        f"/api/v1/content?project_id={created['project_id']}",
        headers={"Authorization": f"Bearer {intruder}"},
    )
    assert filtered.status_code == 404
