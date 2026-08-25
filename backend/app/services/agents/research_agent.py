from app.schemas.agent_outputs import ResearchOutput
from app.services.agents.base import AgentBase
from app.services.agents.kids_shorts_craft import (
    STORY_QUALITY_RULES,
    YOUTUBE_ORIGINAL_RULES,
    format_memory_block,
)


class ResearchAgent(AgentBase[ResearchOutput]):
    """Input: trend + project niche/audience/brand voice.
    Output: research summary, facts, audience insights, opportunities.
    """

    name = "research"
    output_schema = ResearchOutput
    temperature = 0.35

    def build_prompt(self, input_data: dict) -> tuple[str, str]:
        trend = input_data["trend"]
        niche = input_data.get("niche") or "kids entertainment"
        audience = input_data.get("audience") or "young children and parents"
        brand_voice = input_data.get("brand_voice") or "warm, playful, and kid-friendly"
        previous = input_data.get("previous_content") or []
        winners = input_data.get("winning_content") or []
        variety_seed = input_data.get("variety_seed") or "none"

        system_instruction = (
            "You are the Research Agent inside creatoros. Find a specific, "
            "original kids YouTube Short idea inspired by the trend — never "
            "a copy of the trending video itself. Prefer a teachable moment "
            "or a funny little problem a child ages 3-8 would care about. "
            "Never fabricate statistics. "
            f"{YOUTUBE_ORIGINAL_RULES} {STORY_QUALITY_RULES}"
        )
        user_prompt = (
            "Trend to research (inspiration only — do not retell it):\n"
            f"- Title: {trend['title']}\n"
            f"- Source: {trend['source']}\n"
            f"- Popularity score: {trend.get('score')}\n\n"
            "Creator context:\n"
            f"- Niche: {niche}\n"
            f"- Target audience: {audience}\n"
            f"- Brand voice: {brand_voice}\n"
            f"{format_memory_block(previous=previous, winners=winners, variety_seed=variety_seed)}\n\n"
            "Produce a JSON object with:\n"
            "- summary: why this topic can become an original kids Short now\n"
            "- facts: concrete, kid-safe context (no invented studies)\n"
            "- audience_insights: what kids and parents actually enjoy here\n"
            "- opportunities: distinct story/lesson angles that are NOT already "
            "in recent or winning videos"
        )
        return system_instruction, user_prompt
