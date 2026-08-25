from app.schemas.agent_outputs import AnalyticsAgentOutput
from app.services.agents.base import AgentBase


class AnalyticsAgent(AgentBase[AnalyticsAgentOutput]):
    """Interprets stored performance metrics — never invents numbers (M6)."""

    name = "analytics"
    output_schema = AnalyticsAgentOutput

    def build_prompt(self, input_data: dict) -> tuple[str, str]:
        system_instruction = (
            "You are the Analytics Agent inside creatoros. Analyze ONLY the "
            "structured performance data provided. Do not invent metrics, "
            "views, likes, comments, or engagement rates. Clearly separate "
            "observed data from interpretation. If evidence is thin, say so "
            "and set confidence to low."
        )
        user_prompt = (
            f"Project niche: {input_data.get('niche') or 'n/a'}\n"
            f"Audience: {input_data.get('audience') or 'n/a'}\n"
            f"Totals: {input_data.get('totals')}\n"
            f"Top content (observed): {input_data.get('top_content')}\n"
            f"Content performance rows (observed): {input_data.get('content_rows')}\n"
            f"Series summary (observed): {input_data.get('series_summary')}\n\n"
            "Produce a JSON object with:\n"
            "- top_patterns: strong patterns grounded in the observed data\n"
            "- weak_patterns: weak or underperforming patterns grounded in data\n"
            "- observations: factual performance observations (cite numbers from input)\n"
            "- confidence: low | medium | high based on how much data you received"
        )
        return system_instruction, user_prompt
