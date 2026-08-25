from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContentGenerateRequest(BaseModel):
    trend_id: UUID
    format: Literal["short"] = "short"
    async_mode: bool = Field(
        default=True,
        description="When true, enqueue a Redis job and return immediately.",
    )


class ContentGenerateAccepted(BaseModel):
    success: bool = True
    job_id: str
    content_id: UUID
    status: str
    generation_phase: str | None = None


class ContentUpdateRequest(BaseModel):
    script: str | None = Field(default=None, min_length=1, max_length=8000)
    titles: list[str] | None = Field(default=None, min_length=1, max_length=8)
    captions: str | None = Field(default=None, min_length=1, max_length=2000)
    hashtags: list[str] | None = Field(default=None, min_length=1, max_length=20)

    @field_validator("script", "captions")
    @classmethod
    def editable_text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("value must contain non-whitespace characters")
        return value

    @field_validator("titles")
    @classmethod
    def titles_must_not_contain_blank_items(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("titles cannot contain blank items")
        return cleaned

    @field_validator("hashtags")
    @classmethod
    def hashtags_must_not_contain_blank_items(
        cls, value: list[str] | None
    ) -> list[str] | None:
        if value is None:
            return None
        cleaned = [item.strip() for item in value]
        if any(not item.lstrip("#").strip() for item in cleaned):
            raise ValueError("hashtags cannot contain blank items")
        return cleaned


class ContentSuggestRequest(BaseModel):
    target: Literal["script", "titles", "caption", "hashtags"]
    guidance: str | None = Field(default=None, max_length=500)


class ContentSuggestion(BaseModel):
    target: str
    suggestions: list[str]
    rationale: str


class ContentPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    trend_id: UUID
    format: str = "short"
    generation_phase: str | None = None
    research: dict | None = None
    strategy: dict | None = None
    video_plan: dict | None = None
    script: str | None = None
    titles: list[str] | None = None
    captions: str | None = None
    hashtags: list[str] | None = None
    video_url: str | None = None
    thumbnail_url: str | None = None
    publish_status: str = "draft"
    youtube_video_id: str | None = None
    status: str
    error: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    project_name: str | None = None
    trend_title: str | None = None


class ContentExport(BaseModel):
    content_id: UUID
    status: str
    format: str = "markdown"
    filename: str
    body: str
