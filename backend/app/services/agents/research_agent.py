from app.schemas.agent_outputs import ResearchOutput
from app.services.agents.base import AgentBase


class ResearchAgent(AgentBase[ResearchOutput]):
    """Input: trend + project niche/audience/brand voice.
    Output: research summary, facts, audience insights, opportunities.
    """

    name = "research"
    output_schema = ResearchOutput

    def build_prompt(self, input_data: dict) -> tuple[str, str]:
        trend = input_data["trend"]
        niche = input_data.get("niche") or "general content creation"
        audience = input_data.get("audience") or "a general audience"
        brand_voice = input_data.get("brand_voice") or "clear and engaging"

        system_instruction = (
            "You are the Research Agent inside creatoros, an AI content "
            "business automation platform. Given a trending topic, produce "
            "honest, specific research for a content creator. Never "
            "fabricate statistics, studies, or facts you are not confident "
            "about — prefer well-known general knowledge and clearly "
            "reasoned insight over invented specifics."
        )
        user_prompt = (
            "Trend to research:\n"
            f"- Title: {trend['title']}\n"
            f"- Source: {trend['source']}\n"
            f"- Popularity score: {trend.get('score')}\n\n"
            "Creator context:\n"
            f"- Niche: {niche}\n"
            f"- Target audience: {audience}\n"
            f"- Brand voice: {brand_voice}\n\n"
            "Produce a JSON object with:\n"
            "- summary: a concise research summary of why this trend "
            "matters for this niche right now\n"
            "- facts: a list of relevant, specific facts or context about "
            "the trend itself\n"
            "- audience_insights: a list of what this target audience "
            "likely cares about regarding this trend\n"
            "- opportunities: a list of concrete content opportunities this "
            "trend creates for this specific niche"
        )
        return system_instruction, user_prompt
