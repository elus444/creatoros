"""Shared craft rules for original, catchy, YouTube-safer kids Shorts.

These strings are prompt policy, not a guarantee of YPP approval. They steer
agents away from repetitive colorful-clip spam and copied scripts.
"""

from __future__ import annotations

import hashlib
import re

_REPEAT_WORD_RE = re.compile(r"\b(\w+)(?:\s+\1){2,}\b", re.IGNORECASE)
_REPEAT_PHRASE_RE = re.compile(r"\b((?:\w+\s+){1,4}\w+)(?:\s+\1){1,}\b", re.IGNORECASE)

YOUTUBE_ORIGINAL_RULES = (
    "YouTube originality (so the channel can stay eligible to earn): "
    "Every video must be a new original mini-story or lesson, not a template "
    "with one word swapped. Do not copy other YouTube videos, do not reuse "
    "prior narration/titles/scenes, and do not make near-duplicates. If a "
    "past video performed well, make a cousin: same vibe and lesson type, "
    "new setting, new problem, new hook wording, new payoff. Honest titles "
    "only. No fake urgency, no 'smash like or this ends', no subscribe-spam, "
    "no misleading thumbnails-in-words, no shock bait. Give real entertainment "
    "or a tiny teachable moment a parent would be glad a child watched."
)

STORY_QUALITY_RULES = (
    "Story quality: This is a complete Short, not a random 5-second color clip. "
    "Open with a specific hook in the first sentence (a surprise, a problem, "
    "or a funny question) — never a generic 'hey kids' or 'welcome back'. "
    "Then a clear beginning, middle, and satisfying ending. One named "
    "character, one setting, one goal. Fun, warm, and catchy. Motion must "
    "show the story (reaching, spotting, helping, celebrating), not idle "
    "bouncing in a colorful void. Keep it safe for ages 3-8."
)

SPOKEN_VOICE_RULES = (
        "Spoken narration: Natural spoken English a real kids host would say. "
        "Complete sentences. Simple words. Varied rhythm. No broken grammar, "
        "no repeated words, no stuttering loops, no robotic list of scene labels, "
        "no reading the shot list out loud. Do not say you are an AI. Do not "
        "stack CTAs. End on a warm payoff, not 'like and subscribe'. Write one "
        "spoken sentence per video beat so the character's mouth can match the words."
)

VISUAL_VARIETY_RULES = (
    "Visuals: Specific storybook/Pixar-style 9:16 cartoon with a real place "
    "(kitchen, garden, rainy porch, bakery, bedtime room) and matching props. "
    "Do not default to a generic neon playground or random pastel blob. "
    "Same character design across shots. Centered full-body framing, locked "
    "camera, no on-screen text, logos, or captions."
)


def format_memory_block(*, previous: list, winners: list, variety_seed: str) -> str:
    recent = previous[:8] if isinstance(previous, list) else []
    top = winners[:3] if isinstance(winners, list) else []
    return (
        f"Creativity salt (must change hook, setting, and joke): {variety_seed}\n"
        f"Recent videos to avoid cloning: {recent}\n"
        f"Winning videos to make a similar-but-new cousin of: {top or 'none yet'}\n"
        "If winners exist, keep the winning lesson type or character energy, "
        "but invent a new plot. If no winners, pick a story type that is not "
        "already in the recent list."
    )


def normalize_spoken_narration(text: str) -> str:
    """Clean glitchy repeats without inventing new lines."""
    spoken = re.sub(r"\s+", " ", (text or "").strip())
    if not spoken:
        return spoken
    spoken = _REPEAT_WORD_RE.sub(r"\1", spoken)
    spoken = _REPEAT_PHRASE_RE.sub(r"\1", spoken)
    spoken = re.sub(r"\s+", " ", spoken).strip()
    if spoken and spoken[-1] not in ".!?":
        spoken = f"{spoken}."
    return spoken[:2500]


def backdrop_color(concept: str) -> str:
    """One muted storybook color per video so scenes do not flash rainbow."""
    palette = (
        "#F4E4C1",
        "#D7E8D0",
        "#D9ECF5",
        "#F7DCC8",
        "#E6D7F2",
        "#F3E0E0",
        "#DEE8C8",
        "#E8E4D4",
    )
    digest = hashlib.sha256((concept or "short").encode("utf-8")).digest()
    return palette[digest[0] % len(palette)]
