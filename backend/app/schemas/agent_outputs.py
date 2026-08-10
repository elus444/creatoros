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
