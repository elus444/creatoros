"""Unit tests for llm_service's Gemini transport layer.

Network calls are faked at the httpx.AsyncClient level — no real network
access happens in this suite. Live connectivity is verified separately
against the real Gemini API as part of manual milestone verification.
"""

import json

import httpx
import pytest
from pydantic import BaseModel

from app.core.config import get_settings
from app.services.llm_service import (
    LLMNotConfiguredError,
    LLMResponseError,
    LLMService,
    LLMServiceError,
)


class _DummySchema(BaseModel):
    summary: str
    facts: list[str]


def _gemini_response(text: str, *, prompt_tokens: int = 10, completion_tokens: int = 20) -> dict:
    return {
        "candidates": [
            {
                "content": {"parts": [{"text": text}], "role": "model"},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": prompt_tokens,
            "candidatesTokenCount": completion_tokens,
            "totalTokenCount": prompt_tokens + completion_tokens,
        },
    }


class _FakeResponse:
    def __init__(self, json_body: dict, status_code: int = 200) -> None:
        self._json_body = json_body
        self.status_code = status_code
        self.text = json.dumps(json_body)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://generativelanguage.googleapis.com/")
            response = httpx.Response(self.status_code, request=request, json=self._json_body)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def json(self) -> dict:
        return self._json_body


class _FakeAsyncClient:
    captured_payload: dict | None = None
    captured_headers: dict | None = None
    response_body: dict = {}
    response_status: int = 200

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def post(self, url: str, headers: dict, json: dict) -> _FakeResponse:
        type(self).captured_payload = json
        type(self).captured_headers = headers
        return _FakeResponse(self.response_body, self.response_status)


@pytest.fixture(autouse=True)
def _configure_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "gemini_model", "gemini-flash-lite-latest")


@pytest.mark.asyncio
async def test_generate_structured_returns_parsed_data_and_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _gemini_response(json.dumps({"summary": "hello", "facts": ["a", "b"]}))

    class _Client(_FakeAsyncClient):
        response_body = body

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    service = LLMService()
    result = await service.generate_structured(
        prompt="Summarize.", response_model=_DummySchema, system_instruction="Be honest."
    )

    assert result.data == {"summary": "hello", "facts": ["a", "b"]}
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 20
    assert result.total_tokens == 30
    assert result.model == "gemini-flash-lite-latest"


@pytest.mark.asyncio
async def test_request_uses_gemini_schema_format_and_never_logs_key_in_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _gemini_response(json.dumps({"summary": "x", "facts": ["y"]}))

    class _Client(_FakeAsyncClient):
        response_body = body

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    service = LLMService()
    await service.generate_structured(prompt="Go.", response_model=_DummySchema)

    payload = _Client.captured_payload
    schema = payload["generationConfig"]["responseSchema"]
    assert schema["type"] == "OBJECT"
    assert schema["properties"]["summary"]["type"] == "STRING"
    assert schema["properties"]["facts"]["type"] == "ARRAY"
    assert schema["properties"]["facts"]["items"]["type"] == "STRING"
    assert set(schema["required"]) == {"summary", "facts"}
    # The API key must travel only via the header, never embedded in the body.
    assert "test-key" not in json.dumps(payload)
    assert _Client.captured_headers["x-goog-api-key"] == "test-key"


@pytest.mark.asyncio
async def test_missing_api_key_raises_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "gemini_api_key", None)

    service = LLMService()
    with pytest.raises(LLMNotConfiguredError):
        await service.generate_structured(prompt="Go.", response_model=_DummySchema)


@pytest.mark.asyncio
async def test_http_error_raises_llm_service_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Client(_FakeAsyncClient):
        response_body = {"error": {"message": "quota exceeded"}}
        response_status = 429

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    service = LLMService()
    with pytest.raises(LLMServiceError, match="429"):
        await service.generate_structured(prompt="Go.", response_model=_DummySchema)


@pytest.mark.asyncio
async def test_malformed_json_text_raises_response_error(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _gemini_response("not valid json {{{")

    class _Client(_FakeAsyncClient):
        response_body = body

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    service = LLMService()
    with pytest.raises(LLMResponseError):
        await service.generate_structured(prompt="Go.", response_model=_DummySchema)


@pytest.mark.asyncio
async def test_blocked_response_with_no_candidates_raises_response_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Client(_FakeAsyncClient):
        response_body = {"candidates": [{"finishReason": "SAFETY"}]}

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    service = LLMService()
    with pytest.raises(LLMResponseError):
        await service.generate_structured(prompt="Go.", response_model=_DummySchema)
