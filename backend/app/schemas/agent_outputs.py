"""Structured output schemas for the M3/M4 agent pipeline (Constitution §6).

Every agent response is validated against one of these before it is trusted
or persisted — never free-form LLM text. Fields are intentionally flat
(str / list[str]) so they translate directly to Gemini's structured-output
schema format with no nested-object/$ref handling required.
"""

from pydantic import BaseModel, Field


class ResearchOutput(BaseModel):
    """Research Agent output: what's worth knowing about the trend."""

    summary: str = Field(min_length=1, max_length=2000)
    facts: list[str] = Field(min_length=1, max_length=10)
    audience_insights: list[str] = Field(min_length=1, max_length=10)
    opportunities: list[str] = Field(min_length=1, max_length=10)


class StrategyOutput(BaseModel):
    """Strategy Agent output: how to turn the research into a content plan."""

    angle: str = Field(min_length=1, max_length=500)
    hooks: list[str] = Field(min_length=1, max_length=8)
    target_audience: str = Field(min_length=1, max_length=500)
    structure: list[str] = Field(min_length=1, max_length=12)


class ContentOutput(BaseModel):
    """Content Agent output: the actual publishable short-form content."""

    script: str = Field(min_length=1, max_length=5000)
    titles: list[str] = Field(min_length=1, max_length=8)
    caption: str = Field(min_length=1, max_length=2000)
    hashtags: list[str] = Field(min_length=1, max_length=20)


class SuggestionOutput(BaseModel):
    """AI Suggestions Agent output for the Content Workspace (M4)."""

    suggestions: list[str] = Field(min_length=1, max_length=6)
    rationale: str = Field(min_length=1, max_length=1000)


# Planning Agent uses the same structured shape as the historical Strategy
# output (stored in content.strategy). Agent name is now "planning".
PlanningOutput = StrategyOutput


class VideoOutput(BaseModel):
    """Video Agent output: a concrete generation brief (not the final file)."""

    concept: str = Field(min_length=1, max_length=800)
    scenes: list[str] = Field(min_length=1, max_length=16)
    visual_direction: str = Field(min_length=1, max_length=1500)
    narration: str = Field(min_length=1, max_length=8000)
    titles: list[str] = Field(min_length=1, max_length=8)
    caption: str = Field(min_length=1, max_length=2000)
    hashtags: list[str] = Field(min_length=1, max_length=20)
    aspect_ratio: str = Field(pattern="^9:16$")
    duration_seconds: int = Field(ge=5, le=60)


class AnalyticsAgentOutput(BaseModel):
    """Analytics Agent: observed patterns from stored performance data (M6)."""

    top_patterns: list[str] = Field(min_length=1, max_length=8)
    weak_patterns: list[str] = Field(min_length=1, max_length=8)
    observations: list[str] = Field(min_length=1, max_length=10)
    confidence: str = Field(pattern="^(low|medium|high)$")


class CoachRecommendation(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=800)
    action: str = Field(min_length=1, max_length=800)
    priority: str = Field(pattern="^(high|medium|low)$")


class CoachAgentOutput(BaseModel):
    """Coach Agent: actionable recommendations grounded in analytics (M6)."""

    recommendations: list[CoachRecommendation] = Field(min_length=3, max_length=6)
    summary: str = Field(min_length=1, max_length=1000)
