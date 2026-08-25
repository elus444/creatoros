from app.schemas.agent_outputs import VideoOutput
from app.services.agents.base import AgentBase
from app.services.agents.kids_shorts_craft import (
    SPOKEN_VOICE_RULES,
    STORY_QUALITY_RULES,
    VISUAL_VARIETY_RULES,
    YOUTUBE_ORIGINAL_RULES,
    format_memory_block,
)


class VideoAgent(AgentBase[VideoOutput]):
    """Video Agent: turns a plan into a generation brief for video_generation_service.

    Does not call the video provider directly — the orchestrator does.
    """

    name = "video"
    output_schema = VideoOutput
    temperature = 0.72

    def build_prompt(self, input_data: dict) -> tuple[str, str]:
        plan = input_data["strategy"]
        brand_voice = input_data.get("brand_voice") or "warm, playful, and kid-friendly"
        previous = input_data.get("previous_content") or []
        winners = input_data.get("winning_content") or []
        variety_seed = input_data.get("variety_seed") or "none"

        system_instruction = (
            "You are the Video Agent inside creatoros. Write a production "
            "brief for one original kids YouTube Short (ages ~3-8). The "
            "product is MOTION VIDEO with spoken narration: a complete "
            "catchy mini-story, not stills, not on-screen text, not a "
            "random colorful loop. Every shot is a centered vertical 9:16 "
            "medium shot with the full character in frame. "
            f"{YOUTUBE_ORIGINAL_RULES} {STORY_QUALITY_RULES} "
            f"{SPOKEN_VOICE_RULES} {VISUAL_VARIETY_RULES}"
        )
        user_prompt = (
            f"Brand voice: {brand_voice}\n"
            "Format: YouTube Shorts only (aspect_ratio must be 9:16)\n"
            "Audience: young children and parents\n"
            "Duration: 28-45 seconds. Aim for ~55-90 spoken words.\n"
            f"{format_memory_block(previous=previous, winners=winners, variety_seed=variety_seed)}\n\n"
            "Approved plan:\n"
            f"- Angle: {plan['angle']}\n"
            f"- Hooks: {'; '.join(plan['hooks'])}\n"
            f"- Audience: {plan['target_audience']}\n"
            f"- Structure: {' -> '.join(plan['structure'])}\n\n"
            "Produce JSON with:\n"
            "- concept: one sentence with named character, specific place, "
            "the problem, and the payoff\n"
            "- scenes: exactly 3 MOTION beats that tell THAT story in order. Each "
            "line names the character, the place, the action, and that they "
            "are talking. Waist-up so the mouth is visible. Same character "
            "design in every shot. Centered framing, extra margin, locked "
            "camera. No running out of frame, no extreme close-ups, no "
            "on-screen words, no generic 'colorful playground' filler.\n"
            "- visual_direction: story-specific setting, time of day, "
            "wardrobe, and props. Cute Pixar/storybook lighting. Do not "
            "say only 'bright colors'.\n"
            "- narration: a spoken mini-story with one sentence per scene, "
            "in the same order as scenes, so the mouth and the voice match. "
            "Start with the strongest hook. Short sentences a child enjoys. "
            "Never say 'scene one'.\n"
            "- titles: specific, honest Shorts titles parents would click "
            "(not ALL CAPS bait, not copied from the trend title)\n"
            "- caption: a parent-facing description of the story/lesson\n"
            "- hashtags: without #\n"
            "- aspect_ratio: exactly '9:16'\n"
            "- duration_seconds: integer between 28 and 45"
        )
        return system_instruction, user_prompt
