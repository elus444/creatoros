from app.schemas.agent_outputs import StrategyOutput
from app.services.agents.base import AgentBase


class StrategyAgent(AgentBase[StrategyOutput]):
    """Input: Research Agent output (+ creator context).
    Output: content angle, hooks, target audience, video structure.
    """

    name = "strategy"
    output_schema = StrategyOutput

    def build_prompt(self, input_data: dict) -> tuple[str, str]:
        research = input_data["research"]
        niche = input_data.get("niche") or "general content creation"
        brand_voice = input_data.get("brand_voice") or "clear and engaging"

        system_instruction = (
            "You are the Strategy Agent inside creatoros, an AI content "
            "business automation platform. Given research about a trend, "
            "define a concrete, specific short-form video content strategy "
            "— never generic advice that could apply to any topic."
        )
        user_prompt = (
            "Creator context:\n"
            f"- Niche: {niche}\n"
            f"- Brand voice: {brand_voice}\n\n"
            "Research to build a strategy from:\n"
            f"- Summary: {research['summary']}\n"
            f"- Facts: {'; '.join(research['facts'])}\n"
            f"- Audience insights: {'; '.join(research['audience_insights'])}\n"
            f"- Opportunities: {'; '.join(research['opportunities'])}\n\n"
            "Produce a JSON object with:\n"
            "- angle: the specific content angle/take to use for this video\n"
            "- hooks: a list of attention-grabbing opening lines/hooks for "
            "the first few seconds\n"
            "- target_audience: a specific description of who this exact "
            "piece of content is for\n"
            "- structure: an ordered list of the video's structural beats "
            "(e.g. hook, context, payoff, call to action)"
        )
        return system_instruction, user_prompt
