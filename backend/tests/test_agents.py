"""Unit tests for AgentBase's validate/retry logic, using a scripted fake
llm_service so no real LLM or network call happens here.
"""

import pytest
from pydantic import BaseModel

from app.services.agents.base import AgentBase, AgentExecutionError
from app.services.llm_service import LLMNotConfiguredError, LLMResult, LLMServiceError


class _Output(BaseModel):
    summary: str
    facts: list[str]


class _Agent(AgentBase[_Output]):
    name = "test_agent"
    output_schema = _Output

    def build_prompt(self, input_data: dict) -> tuple[str, str]:
        return "system", f"prompt for {input_data.get('topic', 'unknown')}"


class _ScriptedLLMService:
    """Returns/raises each item in `script`, in order, one per call."""

    def __init__(self, script: list) -> None:
        self._script = list(script)
        self.calls: list[dict] = []

    async def generate_structured(
        self, *, prompt: str, response_model: type[BaseModel], system_instruction=None, temperature=0.4
    ) -> LLMResult:
        self.calls.append({"prompt": prompt, "response_model": response_model})
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _result(data: dict) -> LLMResult:
    return LLMResult(
        data=data,
        raw_text=str(data),
        model="test-model",
        prompt_tokens=5,
        completion_tokens=10,
        total_tokens=15,
    )


@pytest.mark.asyncio
async def test_succeeds_on_first_attempt() -> None:
    llm = _ScriptedLLMService([_result({"summary": "ok", "facts": ["a"]})])
    agent = _Agent(llm)

    result = await agent.run({"topic": "bread"})

    assert result.output.summary == "ok"
    assert len(result.attempts) == 1
    assert result.attempts[0].status == "success"
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_retries_after_validation_error_then_succeeds() -> None:
    llm = _ScriptedLLMService(
        [
            _result({"summary": "ok"}),  # missing required "facts" -> ValidationError
            _result({"summary": "ok", "facts": ["a", "b"]}),
        ]
    )
    agent = _Agent(llm)

    result = await agent.run({"topic": "bread"})

    assert result.output.facts == ["a", "b"]
    assert len(result.attempts) == 2
    assert result.attempts[0].status == "failed"
    assert result.attempts[1].status == "success"
    # The corrective retry prompt must reference the earlier failure.
    assert "rejected" in llm.calls[1]["prompt"]


@pytest.mark.asyncio
async def test_retries_after_transport_error_then_succeeds() -> None:
    llm = _ScriptedLLMService(
        [
            LLMServiceError("Gemini API returned HTTP 500"),
            _result({"summary": "ok", "facts": ["a"]}),
        ]
    )
    agent = _Agent(llm)

    result = await agent.run({"topic": "bread"})

    assert result.output.summary == "ok"
    assert len(result.attempts) == 2
    assert result.attempts[0].error == "Gemini API returned HTTP 500"


@pytest.mark.asyncio
async def test_exhausts_retries_and_raises() -> None:
    llm = _ScriptedLLMService(
        [
            _result({"summary": "bad"}),
            _result({"summary": "bad"}),
            _result({"summary": "bad"}),
        ]
    )
    agent = _Agent(llm)

    with pytest.raises(AgentExecutionError) as exc_info:
        await agent.run({"topic": "bread"})

    assert exc_info.value.agent_name == "test_agent"
    assert len(exc_info.value.attempts) == 3
    assert all(attempt.status == "failed" for attempt in exc_info.value.attempts)
    assert len(llm.calls) == 3


@pytest.mark.asyncio
async def test_not_configured_fails_fast_without_retrying() -> None:
    llm = _ScriptedLLMService([LLMNotConfiguredError("GEMINI_API_KEY is not set")])
    agent = _Agent(llm)

    with pytest.raises(AgentExecutionError) as exc_info:
        await agent.run({"topic": "bread"})

    assert len(exc_info.value.attempts) == 1
    assert len(llm.calls) == 1
