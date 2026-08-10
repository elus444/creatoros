from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TrendPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    title: str
    source: str
    url: str
    score: float
    metrics: dict | None = None
    is_selected: bool
    created_at: datetime


class TrendCollectRequest(BaseModel):
    """Optional override for what to search; defaults to the project's niche/name."""

    query: str | None = Field(default=None, max_length=200)


class TrendCollectResponse(BaseModel):
    trends: list[TrendPublic]
    collected: int
    sources_used: list[str]
    warnings: list[str] = Field(default_factory=list)
