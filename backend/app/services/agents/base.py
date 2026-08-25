"""Agent base abstraction (Constitution §5-6).

Every agent:
  - has a clearly defined input (a plain dict the orchestrator builds)
  - has a clearly defined, validated structured output (a Pydantic model)
  - never talks to an LLM provider directly — only through `llm_service`
  - never bypasses the orchestrator (agents don't call each other)

`AgentBase.run()` owns the "validate every response; retry malformed ones"
rule: each attempt is recorded (success or failure) so the orchestrator can
persist a full, honest `agent_runs` trail, including retries.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel, ValidationError

from app.services.llm_service import LLMNotConfiguredError, LLMService, LLMServiceError

TOutput = TypeVar("TOutput", bound=BaseModel)


@dataclass
class AgentAttempt:
    attempt: int
    status: str  # "success" | "failed"
    output: dict | None
    error: str | None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class AgentExecutionError(Exception):
    """Raised when an agent exhausts every attempt without valid output.

    Carries every attempt made so the caller can log the full retry trail
    before surfacing a clear failure — never a silent/fabricated fallback.
    """

    def __init__(self, agent_name: str, attempts: list[AgentAttempt]) -> None:
        self.agent_name = agent_name
        self.attempts = attempts
        last_error = attempts[-1].error if attempts else "unknown error"
        super().__init__(
            f"{agent_name} agent failed after {len(attempts)} attempt(s): {last_error}"
        )


@dataclass
class AgentExecutionResult(Generic[TOutput]):
    output: TOutput
    attempts: list[AgentAttempt]


class AgentBase(ABC, Generic[TOutput]):
    name: str
    output_schema: type[TOutput]
    max_attempts: int = 3  # 1 initial attempt + up to 2 corrective retries
    temperature: float = 0.4

    def __init__(self, llm_service: LLMService) -> None:
        self.llm_service = llm_service

    @abstractmethod
    def build_prompt(self, input_data: dict) -> tuple[str, str]:
        """Returns (system_instruction, user_prompt) built from `input_data`."""
        raise NotImplementedError

    async def run(self, input_data: dict) -> AgentExecutionResult[TOutput]:
        attempts: list[AgentAttempt] = []
        system_instruction, base_prompt = self.build_prompt(input_data)
        correction: str | None = None

        for attempt_number in range(1, self.max_attempts + 1):
            prompt = base_prompt
            if correction:
                prompt = (
                    f"{base_prompt}\n\n"
                    f"Your previous response was rejected for this reason: {correction}\n"
                    "Provide a corrected response that strictly satisfies the schema."
                )

            try:
                result = await self.llm_service.generate_structured(
                    prompt=prompt,
                    response_model=self.output_schema,
                    system_instruction=system_instruction,
                    temperature=self.temperature,
                )
            except LLMNotConfiguredError as exc:
                # Retrying can never help if there's no API key — fail fast
                # rather than burning attempts, mirroring
                # CollectorNotConfiguredError's short-circuit behavior.
                attempts.append(
                    AgentAttempt(
                        attempt=attempt_number, status="failed", output=None, error=str(exc)
                    )
                )
                raise AgentExecutionError(self.name, attempts) from exc
            except LLMServiceError as exc:
                attempts.append(
                    AgentAttempt(
                        attempt=attempt_number, status="failed", output=None, error=str(exc)
                    )
                )
                correction = str(exc)
                continue

            try:
                validated = self.output_schema.model_validate(result.data)
            except ValidationError as exc:
                attempts.append(
                    AgentAttempt(
                        attempt=attempt_number,
                        status="failed",
                        output=result.data,
                        error=str(exc),
                        prompt_tokens=result.prompt_tokens,
                        completion_tokens=result.completion_tokens,
                        total_tokens=result.total_tokens,
                    )
                )
                correction = str(exc)
                continue

            attempts.append(
                AgentAttempt(
                    attempt=attempt_number,
                    status="success",
                    output=validated.model_dump(),
                    error=None,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                    total_tokens=result.total_tokens,
                )
            )
            return AgentExecutionResult(output=validated, attempts=attempts)

        raise AgentExecutionError(self.name, attempts)
