from app.schemas.agent_outputs import PlanningOutput
from app.services.agents.base import AgentBase
from app.services.agents.kids_shorts_craft import (
    SPOKEN_VOICE_RULES,
    STORY_QUALITY_RULES,
    YOUTUBE_ORIGINAL_RULES,
    format_memory_block,
)


class PlanningAgent(AgentBase[PlanningOutput]):
    """Planning Agent (formerly Strategy): produces a VIDEO PLAN.

    Output is stored on content.strategy for schema compatibility.
    """

    name = "planning"
    output_schema = PlanningOutput
    temperature = 0.62

    def build_prompt(self, input_data: dict) -> tuple[str, str]:
        research = input_data["research"]
        niche = input_data.get("niche") or "kids entertainment"
        brand_voice = input_data.get("brand_voice") or "warm, playful, and kid-friendly"
        previous = input_data.get("previous_content") or []
        winners = input_data.get("winning_content") or []
        variety_seed = input_data.get("variety_seed") or "none"

        system_instruction = (
            "You are the Planning Agent inside creatoros. Write a concrete "
            "plan for one complete 9:16 kids YouTube Short (about 30-55 "
            "seconds), not a blog outline and not a random color montage. "
            f"{YOUTUBE_ORIGINAL_RULES} {STORY_QUALITY_RULES} {SPOKEN_VOICE_RULES}"
        )
        user_prompt = (
            "Creator context:\n"
            f"- Niche: {niche}\n"
            f"- Brand voice: {brand_voice}\n"
            "- Format: YouTube Shorts only (9:16). Full mini-story, 30-55s.\n"
            f"{format_memory_block(previous=previous, winners=winners, variety_seed=variety_seed)}\n\n"
            "Research:\n"
            f"- Summary: {research['summary']}\n"
            f"- Facts: {'; '.join(research['facts'])}\n"
            f"- Audience insights: {'; '.join(research['audience_insights'])}\n"
            f"- Opportunities: {'; '.join(research['opportunities'])}\n\n"
            "Produce a JSON object with:\n"
            "- angle: one original story in one sentence (named character + "
            "setting + problem + payoff)\n"
            "- hooks: 2-4 cold-open lines a child would stay for; each must "
            "be specific and different from recent hooks\n"
            "- target_audience: kids ~3-8 and the parent watching with them\n"
            "- structure: 4-6 ordered VIDEO beats: hook, setup, try/fail or "
            "discovery, payoff, warm close. No subscribe-spam beat."
        )
        return system_instruction, user_prompt


# Back-compat alias used by older imports/tests during transition.
StrategyAgent = PlanningAgent
