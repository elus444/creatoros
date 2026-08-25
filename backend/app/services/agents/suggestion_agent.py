from app.schemas.agent_outputs import SuggestionOutput
from app.services.agents.base import AgentBase


class SuggestionAgent(AgentBase[SuggestionOutput]):
    """Produces alternative options for one editable content field.

    Does not mutate content itself — the orchestrator returns suggestions
    to the workspace and the user chooses what to apply.
    """

    name = "suggestion"
    output_schema = SuggestionOutput

    def build_prompt(self, input_data: dict) -> tuple[str, str]:
        target = input_data["target"]
        current = input_data.get("current")
        guidance = input_data.get("guidance") or "Improve clarity and engagement."
        brand_voice = input_data.get("brand_voice") or "clear and engaging"
        strategy = input_data.get("strategy") or {}

        system_instruction = (
            "You are the Suggestion Agent inside creatoros. Given one piece of "
            "existing short-form content, propose concrete alternatives the "
            "creator can apply. Stay specific to the given strategy and brand "
            "voice — never invent a new topic."
        )
        user_prompt = (
            f"Brand voice: {brand_voice}\n"
            f"Strategy angle: {strategy.get('angle', 'n/a')}\n"
            f"Target field: {target}\n"
            f"Current value: {current}\n"
            f"Creator guidance: {guidance}\n\n"
            "Produce a JSON object with:\n"
            "- suggestions: a list of alternative values for that field "
            "(for titles/hashtags, each suggestion is one complete option "
            "string; for script/caption, each suggestion is a full rewrite)\n"
            "- rationale: a short explanation of what you improved"
        )
        return system_instruction, user_prompt
