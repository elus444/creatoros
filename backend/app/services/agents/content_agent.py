"""Backward-compatible import path — ContentAgent replaced by VideoAgent.

Tests that still script ContentOutput should migrate to VideoOutput.
"""

from app.schemas.agent_outputs import ContentOutput, VideoOutput
from app.services.agents.base import AgentBase
from app.services.agents.video_agent import VideoAgent


class ContentAgent(AgentBase[ContentOutput]):
    """Deprecated text Content Agent kept only for legacy unit tests.

    Production orchestration uses VideoAgent.
    """

    name = "content"
    output_schema = ContentOutput

    def build_prompt(self, input_data: dict) -> tuple[str, str]:
        strategy = input_data["strategy"]
        brand_voice = input_data.get("brand_voice") or "clear and engaging"
        system_instruction = (
            "You are a legacy Content Agent. Prefer VideoAgent for production."
        )
        user_prompt = (
            f"Brand voice: {brand_voice}\n"
            f"Angle: {strategy['angle']}\n"
            f"Hooks: {', '.join(strategy['hooks'])}\n"
            f"Audience: {strategy['target_audience']}\n"
            f"Structure: {' -> '.join(strategy['structure'])}\n"
            "Produce script, titles, caption, hashtags."
        )
        return system_instruction, user_prompt


__all__ = ["ContentAgent", "VideoAgent", "ContentOutput", "VideoOutput"]
