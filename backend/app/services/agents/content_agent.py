from app.schemas.agent_outputs import ContentOutput
from app.services.agents.base import AgentBase


class ContentAgent(AgentBase[ContentOutput]):
    """Input: Strategy Agent output (+ creator brand voice).
    Output: short-form script, title options, caption, hashtags.
    """

    name = "content"
    output_schema = ContentOutput

    def build_prompt(self, input_data: dict) -> tuple[str, str]:
        strategy = input_data["strategy"]
        brand_voice = input_data.get("brand_voice") or "clear and engaging"

        system_instruction = (
            "You are the Content Agent inside creatoros, an AI content "
            "business automation platform. Given an approved content "
            "strategy, write the actual publishable short-form video "
            "content in the creator's brand voice. Be concrete and usable, "
            "not a generic outline."
        )
        user_prompt = (
            f"Brand voice: {brand_voice}\n\n"
            "Strategy to write from:\n"
            f"- Angle: {strategy['angle']}\n"
            f"- Hooks to consider: {'; '.join(strategy['hooks'])}\n"
            f"- Target audience: {strategy['target_audience']}\n"
            f"- Structure: {' -> '.join(strategy['structure'])}\n\n"
            "Produce a JSON object with:\n"
            "- script: a complete short-form video script (roughly "
            "30-90 seconds spoken) that follows the given structure\n"
            "- titles: a list of punchy, specific title options for the "
            "video\n"
            "- caption: one ready-to-post social media caption\n"
            "- hashtags: a list of relevant hashtags, without the # symbol"
        )
        return system_instruction, user_prompt
