"""Shared LLM + video provider fakes for content/video pipeline tests."""

from __future__ import annotations

import pytest

from app.schemas.agent_outputs import ResearchOutput, StrategyOutput, VideoOutput
from app.services.llm_service import LLMResult, LLMService
from app.services.video_generation_service import VideoGenerationResult, VideoGenerationService

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
    "concept": "One-pan pasta in under a minute of screen time.",
    "scenes": ["hook pan", "ingredients drop", "stir", "plated payoff", "cta"],
    "visual_direction": "Bright kitchen, overhead cuts, vertical framing.",
    "narration": "Open on a single pan. Say: you only need one pan for this...",
    "titles": ["One Pan, Five Minutes, Zero Dishes"],
    "caption": "The easiest pasta you'll make all week. Recipe below!",
    "hashtags": ["easyrecipes", "onepanmeals"],
    "aspect_ratio": "9:16",
    "duration_seconds": 10,
}


def llm_result(data: dict) -> LLMResult:
    return LLMResult(
        data=data,
        raw_text=str(data),
        model="gemini-flash-lite-latest",
        prompt_tokens=12,
        completion_tokens=34,
        total_tokens=46,
    )


def install_fake_llm(monkeypatch: pytest.MonkeyPatch, script: dict[type, list]) -> list:
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


def install_fake_video_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_generate(
        self, *, brief, format="short", owner_id=None, video_provider=None
    ):
        owner = owner_id or "test-owner"
        return VideoGenerationResult(
            video_url="https://cdn.example.com/videos/test.mp4",
            thumbnail_url="https://cdn.example.com/videos/test.jpg",
            storage_key=f"videos/{owner}/test.mp4",
            provider="test",
        )

    monkeypatch.setattr(VideoGenerationService, "generate", fake_generate)


def full_pipeline_script(**overrides) -> dict[type, list]:
    script = {
        ResearchOutput: [llm_result(VALID_RESEARCH)],
        StrategyOutput: [llm_result(VALID_STRATEGY)],
        VideoOutput: [llm_result(VALID_VIDEO)],
    }
    script.update(overrides)
    return script


GENERATE_BODY = {"async_mode": False, "format": "short"}
