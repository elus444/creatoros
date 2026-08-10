from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ContentGenerateRequest(BaseModel):
    trend_id: UUID


class ContentUpdateRequest(BaseModel):
    script: str | None = Field(default=None, min_length=1, max_length=5000)
    titles: list[str] | None = Field(default=None, min_length=1, max_length=8)
    captions: str | None = Field(default=None, min_length=1, max_length=2000)
    hashtags: list[str] | None = Field(default=None, min_length=1, max_length=20)


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
    research: dict | None = None
    strategy: dict | None = None
    script: str | None = None
    titles: list[str] | None = None
    captions: str | None = None
    hashtags: list[str] | None = None
    status: str
    error: str | None = None
    created_at: datetime
    # Enriched for library/workspace display — not stored on the content row.
    project_name: str | None = None
    trend_title: str | None = None


class ContentExport(BaseModel):
    content_id: UUID
    status: str
    format: str = "markdown"
    filename: str
    body: str
