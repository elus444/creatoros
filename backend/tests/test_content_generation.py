"""Integration tests for the Research -> Strategy -> Content pipeline and the
`POST /content/generate` endpoint. The Gemini transport itself is faked at
`LLMService.generate_structured` (same convention as patching collectors'
`collect` methods elsewhere in this suite) so no real network/LLM call
happens here — live connectivity is verified separately.
"""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.models.agent_run import AgentRun
from app.schemas.agent_outputs import ContentOutput, ResearchOutput, StrategyOutput
from app.services.collectors import CollectedItem
from app.services.collectors.youtube_collector import YouTubeCollector
from app.services.llm_service import LLMResult, LLMService, LLMServiceError

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
VALID_CONTENT = {
    "script": "Open on a single pan. Say: you only need one pan for this...",
    "titles": ["One Pan, Five Minutes, Zero Dishes"],
    "caption": "The easiest pasta you'll make all week. Recipe below!",
    "hashtags": ["easyrecipes", "onepanmeals"],
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


def _install_fake_llm(monkeypatch: pytest.MonkeyPatch, script: dict[type, list]) -> list:
    calls: list[type] = []

    async def fake_generate_structured(
        self, *, prompt, response_model, system_instruction=None, temperature=0.4
    ):
        calls.append(response_model)
        items = script.get(response_model)
        if not items:
            raise AssertionError(f"No scripted response left for {response_model}")
        item = items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(LLMService, "generate_structured", fake_generate_structured)
    return calls


def _create_project(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/projects",
        json={
            "name": "Cooking Channel",
            "niche": "quick recipes",
            "audience": "busy home cooks",
            "brand_voice": "upbeat and practical",
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_trend(
    client: TestClient,
    headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    *,
    select: bool = True,
) -> tuple[str, str]:
    project_id = _create_project(client, headers)

    async def fake_youtube_collect(self, query, limit=10):
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
    collect_response = client.post(
        f"/api/v1/projects/{project_id}/trends/collect", headers=headers
    )
    trend_id = collect_response.json()["trends"][0]["id"]
    if select:
        select_response = client.post(
            f"/api/v1/projects/{project_id}/trends/{trend_id}/select",
            headers=headers,
        )
        assert select_response.status_code == 200
        assert select_response.json()["is_selected"] is True
    return project_id, trend_id


def test_generate_content_runs_full_pipeline_and_persists(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, trend_id = _create_trend(client, auth_headers, monkeypatch)
    calls = _install_fake_llm(
        monkeypatch,
        {
            ResearchOutput: [_llm_result(VALID_RESEARCH)],
            StrategyOutput: [_llm_result(VALID_STRATEGY)],
            ContentOutput: [_llm_result(VALID_CONTENT)],
        },
    )

    response = client.post(
        "/api/v1/content/generate", json={"trend_id": trend_id}, headers=auth_headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "GENERATED"
    assert body["research"]["summary"] == VALID_RESEARCH["summary"]
    assert body["strategy"]["angle"] == VALID_STRATEGY["angle"]
    assert body["script"] == VALID_CONTENT["script"]
    assert body["titles"] == VALID_CONTENT["titles"]
    assert body["captions"] == VALID_CONTENT["caption"]
    assert body["hashtags"] == VALID_CONTENT["hashtags"]
    assert body["error"] is None
    assert calls == [ResearchOutput, StrategyOutput, ContentOutput]

    db = client.session_local()
    try:
        runs = db.query(AgentRun).filter(AgentRun.content_id == UUID(body["id"])).all()
        assert len(runs) == 3
        assert [run.agent_name for run in runs] == ["research", "strategy", "content"]
        assert all(run.status == "success" for run in runs)
        assert all(run.tokens == {"prompt": 12, "completion": 34, "total": 46} for run in runs)
    finally:
        db.close()


def test_generate_content_persists_failed_retry_attempts(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, trend_id = _create_trend(client, auth_headers, monkeypatch)
    _install_fake_llm(
        monkeypatch,
        {
            ResearchOutput: [
                _llm_result({"summary": "ok"}),  # missing fields -> retried
                _llm_result(VALID_RESEARCH),
            ],
            StrategyOutput: [_llm_result(VALID_STRATEGY)],
            ContentOutput: [_llm_result(VALID_CONTENT)],
        },
    )

    response = client.post(
        "/api/v1/content/generate", json={"trend_id": trend_id}, headers=auth_headers
    )

    assert response.status_code == 201
    assert response.json()["status"] == "GENERATED"

    db = client.session_local()
    try:
        research_runs = (
            db.query(AgentRun)
            .filter(AgentRun.agent_name == "research")
            .order_by(AgentRun.attempt)
            .all()
        )
        assert len(research_runs) == 2
        assert research_runs[0].status == "failed"
        assert research_runs[0].error is not None
        assert research_runs[1].status == "success"
    finally:
        db.close()


def test_generate_content_fails_after_exhausting_retries(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, trend_id = _create_trend(client, auth_headers, monkeypatch)
    _install_fake_llm(
        monkeypatch,
        {
            ResearchOutput: [LLMServiceError("Gemini API returned HTTP 500")] * 3,
        },
    )

    response = client.post(
        "/api/v1/content/generate", json={"trend_id": trend_id}, headers=auth_headers
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert isinstance(detail, dict)
    assert "Content generation failed" in detail["message"]
    assert detail["content_id"]

    db = client.session_local()
    try:
        from app.models.content import Content

        content = db.query(Content).filter(Content.trend_id == UUID(trend_id)).one()
        assert content.status == "FAILED"
        assert content.error is not None

        runs = db.query(AgentRun).filter(AgentRun.content_id == content.id).all()
        assert len(runs) == 3
        assert all(run.status == "failed" for run in runs)
    finally:
        db.close()


def test_generate_content_requires_auth(client: TestClient) -> None:
    response = client.post(
        "/api/v1/content/generate",
        json={"trend_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 401


def test_generate_content_404_for_nonexistent_trend(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/content/generate",
        json={"trend_id": "00000000-0000-0000-0000-000000000000"},
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_generate_content_requires_ownership(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, trend_id = _create_trend(client, auth_headers, monkeypatch)

    intruder_token = client.post(
        "/api/v1/auth/register",
        json={"email": "intruder-content@example.com", "password": "securepass1"},
    ).json()["access_token"]

    response = client.post(
        "/api/v1/content/generate",
        json={"trend_id": trend_id},
        headers={"Authorization": f"Bearer {intruder_token}"},
    )
    assert response.status_code == 404


def test_generate_content_requires_selected_trend(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, trend_id = _create_trend(client, auth_headers, monkeypatch, select=False)
    _install_fake_llm(
        monkeypatch,
        {
            ResearchOutput: [_llm_result(VALID_RESEARCH)],
            StrategyOutput: [_llm_result(VALID_STRATEGY)],
            ContentOutput: [_llm_result(VALID_CONTENT)],
        },
    )

    response = client.post(
        "/api/v1/content/generate", json={"trend_id": trend_id}, headers=auth_headers
    )
    assert response.status_code == 400
    assert "Select this trend" in response.json()["detail"]


def test_get_content_returns_owned_package(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, trend_id = _create_trend(client, auth_headers, monkeypatch)
    _install_fake_llm(
        monkeypatch,
        {
            ResearchOutput: [_llm_result(VALID_RESEARCH)],
            StrategyOutput: [_llm_result(VALID_STRATEGY)],
            ContentOutput: [_llm_result(VALID_CONTENT)],
        },
    )
    created = client.post(
        "/api/v1/content/generate", json={"trend_id": trend_id}, headers=auth_headers
    ).json()

    fetched = client.get(f"/api/v1/content/{created['id']}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]
    assert fetched.json()["script"] == VALID_CONTENT["script"]
