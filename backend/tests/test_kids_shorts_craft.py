"""Kids Shorts craft: original stories, cleaner speech, winner-aware prompts."""

from app.services.agents.kids_shorts_craft import (
    backdrop_color,
    normalize_spoken_narration,
)
from app.services.agents.video_agent import VideoAgent
from app.services.agents.planning_agent import PlanningAgent


def test_normalize_spoken_narration_collapses_glitchy_repeats() -> None:
    cleaned = normalize_spoken_narration("go go go now friends friends friends")
    assert "go go go" not in cleaned.lower()
    assert cleaned.endswith(".")
    assert "now" in cleaned.lower()


def test_normalize_spoken_narration_keeps_real_sentences() -> None:
    spoken = "Where did the red sock go? Fox looks under the bed and finds it."
    assert normalize_spoken_narration(spoken) == spoken


def test_backdrop_color_is_stable_per_concept() -> None:
    first = backdrop_color("Fox finds a missing sock")
    second = backdrop_color("Fox finds a missing sock")
    other = backdrop_color("Bunny bakes a tiny cake")
    assert first == second
    assert first.startswith("#")
    assert first != other


def test_video_agent_prompt_asks_for_original_full_story() -> None:
    agent = VideoAgent(llm_service=object())
    system, user = agent.build_prompt(
        {
            "strategy": {
                "angle": "Fox hunts a missing sock before bedtime",
                "hooks": ["Where did the red sock go?"],
                "target_audience": "kids 3-8",
                "structure": ["hook", "search", "find", "celebrate"],
            },
            "previous_content": [
                {"title": "Count with Fox", "angle": "counting apples"}
            ],
            "winning_content": [
                {
                    "title": "Count with Fox",
                    "views": 1200,
                    "concept": "fox counts apples",
                    "note": "Make a cousin of this, not a copy.",
                }
            ],
            "variety_seed": "ab12cd",
        }
    )
    blob = f"{system}\n{user}".lower()
    assert "cousin" in blob
    assert "ab12cd" in user
    assert "28-45" in user
    assert "smash like" in blob
    assert "exactly 3" in user
    assert "one sentence per scene" in user
    assert "mouth" in blob
    assert "count with fox" in user.lower()


def test_planning_agent_prompt_rejects_short_color_clips() -> None:
    agent = PlanningAgent(llm_service=object())
    system, user = agent.build_prompt(
        {
            "research": {
                "summary": "Kids love hide and seek objects.",
                "facts": ["Toddlers like repetition with a twist."],
                "audience_insights": ["Parents want a payoff."],
                "opportunities": ["A sock-search bedtime story."],
            },
            "winning_content": [],
            "previous_content": [],
            "variety_seed": "seed1",
        }
    )
    blob = f"{system}\n{user}".lower()
    assert "30-55" in blob
    assert "subscribe-spam" in blob
    assert "seed1" in user
