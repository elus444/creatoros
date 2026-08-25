"""The one and only gateway to an LLM provider (Constitution §5).

Agents must never independently create their own LLM clients:

    Agent -> llm_service -> LLM Provider

This module owns all HTTP/auth/transport details for Google Gemini's
`generateContent` REST API (verified live during implementation — "fully
supported", not the newer Interactions API, since our agents only need
single-turn structured calls with no server-side conversation state).

llm_service is intentionally provider-transport-only: it sends the prompt,
asks Gemini to shape its JSON output around the caller's Pydantic schema,
and parses that JSON. It does NOT validate the result against the schema's
business rules (e.g. `min_length`) — that's the agent base's job, since
"validate every response, retry malformed ones" is agent/orchestration
logic, not transport logic.
"""

import json
import logging
from dataclasses import dataclass

import httpx
from pydantic import BaseModel

from app.core.config import get_settings

logger = logging.getLogger("creatoros.llm")

_TYPE_MAP = {
    "object": "OBJECT",
    "string": "STRING",
    "array": "ARRAY",
    "integer": "INTEGER",
    "number": "NUMBER",
    "boolean": "BOOLEAN",
}


class LLMServiceError(Exception):
    """Raised for transport-level failures: network, HTTP, or malformed
    provider responses. Never raised with the API key in the message.
    """


class LLMNotConfiguredError(LLMServiceError):
    """Raised when GEMINI_API_KEY is missing — fail clearly, never fake a
    response (Constitution §16/§25).
    """


class LLMResponseError(LLMServiceError):
    """Raised when the provider responded but gave no usable/parseable text
    (e.g. blocked by safety filters, empty candidates, invalid JSON).
    """


@dataclass
class LLMResult:
    data: dict
    raw_text: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None


def _convert_schema_node(node: dict) -> dict:
    """Converts one node of a Pydantic-generated JSON Schema into Gemini's
    structured-output schema format (uppercase type names; verified live
    against the real API). Only handles what our flat agent-output schemas
    (str / list[str] fields) actually produce — no $ref/$defs resolution,
    since none of our schemas nest sub-models.
    """
    node_type = node.get("type")
    converted: dict = {}
    if node_type in _TYPE_MAP:
        converted["type"] = _TYPE_MAP[node_type]

    if node_type == "object":
        properties = node.get("properties", {})
        converted["properties"] = {
            key: _convert_schema_node(value) for key, value in properties.items()
        }
        if "required" in node:
            converted["required"] = node["required"]
    elif node_type == "array" and "items" in node:
        converted["items"] = _convert_schema_node(node["items"])
        for key in ("minItems", "maxItems"):
            if key in node:
                converted[key] = node[key]
    return converted


def _pydantic_to_gemini_schema(model: type[BaseModel]) -> dict:
    return _convert_schema_node(model.model_json_schema())


def _safe_error_detail(response: httpx.Response) -> str:
    """Extracts a human-readable error message without ever including
    request headers (where the API key lives) in what gets logged/raised.
    """
    try:
        body = response.json()
        message = body.get("error", {}).get("message")
        if message:
            return str(message)[:400]
    except (ValueError, AttributeError, TypeError):
        pass
    return (response.text or "no details")[:400]


class LLMService:
    """Thin, provider-transport-only wrapper around Gemini's generateContent
    REST API. See module docstring for why raw REST (via the httpx
    dependency we already have) instead of a new SDK dependency.
    """

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout

    async def generate_structured(
        self,
        *,
        prompt: str,
        response_model: type[BaseModel],
        system_instruction: str | None = None,
        temperature: float = 0.4,
    ) -> LLMResult:
        settings = get_settings()
        api_key = settings.gemini_api_key
        if not api_key:
            raise LLMNotConfiguredError(
                "GEMINI_API_KEY is not set; LLM generation is disabled."
            )

        model = settings.gemini_model
        payload: dict = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": _pydantic_to_gemini_schema(response_model),
                "temperature": temperature,
            },
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        url = f"{self.BASE_URL}/{model}:generateContent"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    url,
                    headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
                response_json = response.json()
        except httpx.HTTPStatusError as exc:
            raise LLMServiceError(
                f"Gemini API returned HTTP {exc.response.status_code}: "
                f"{_safe_error_detail(exc.response)}"
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMServiceError(f"Gemini API request failed: {exc}") from exc
        except (TypeError, ValueError) as exc:
            # A non-JSON 2xx response is a provider response failure, not an
            # unhandled application exception. AgentBase can then retry it
            # and persist the failed attempt like every other LLM failure.
            raise LLMResponseError(
                "Gemini API returned an unparseable JSON response"
            ) from exc

        try:
            candidates = response_json["candidates"]
            parts = candidates[0]["content"]["parts"]
            raw_text = "".join(part.get("text", "") for part in parts if "text" in part)
        except (KeyError, IndexError, TypeError) as exc:
            finish_reason = None
            if response_json.get("candidates"):
                finish_reason = response_json["candidates"][0].get("finishReason")
            raise LLMResponseError(
                f"Gemini API response had no usable text (finishReason={finish_reason})"
            ) from exc

        if not raw_text.strip():
            raise LLMResponseError("Gemini API returned an empty response")

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise LLMResponseError("Gemini API did not return valid JSON") from exc

        usage = response_json.get("usageMetadata", {})
        return LLMResult(
            data=data,
            raw_text=raw_text,
            model=model,
            prompt_tokens=usage.get("promptTokenCount"),
            completion_tokens=usage.get("candidatesTokenCount"),
            total_tokens=usage.get("totalTokenCount"),
        )
