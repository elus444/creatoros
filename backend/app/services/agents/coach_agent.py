from app.schemas.agent_outputs import CoachAgentOutput
from app.services.agents.base import AgentBase


class CoachAgent(AgentBase[CoachAgentOutput]):
    """Turns analytics insights into concrete creator actions (M6).

    Must not merely restate the Analytics Agent — convert patterns into
    prioritized, actionable recommendations grounded in provided evidence.
    """

    name = "coach"
    output_schema = CoachAgentOutput

    def build_prompt(self, input_data: dict) -> tuple[str, str]:
        system_instruction = (
            "You are the Coach Agent inside creatoros. Convert performance "
            "insights into practical next actions for the creator. Do not "
            "fabricate evidence. Every recommendation must be grounded in the "
            "provided analytics data and analytics-agent observations. Do not "
            "simply repeat the analytics agent output — translate it into "
            "specific actions the creator can take this week."
        )
        user_prompt = (
            f"Project niche: {input_data.get('niche') or 'n/a'}\n"
            f"Audience: {input_data.get('audience') or 'n/a'}\n"
            f"Brand voice: {input_data.get('brand_voice') or 'n/a'}\n"
            f"Observed totals: {input_data.get('totals')}\n"
            f"Top content (observed): {input_data.get('top_content')}\n"
            f"Analytics agent output: {input_data.get('analytics_insights')}\n"
            f"Recent content context: {input_data.get('recent_content')}\n\n"
            "Produce a JSON object with:\n"
            "- recommendations: at least 3 items, each with title, reason, "
            "action, and priority (high|medium|low)\n"
            "- summary: a short coach overview of what to focus on next"
        )
        return system_instruction, user_prompt
