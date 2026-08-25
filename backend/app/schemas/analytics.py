"""Analytics request/response schemas (M6)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class AnalyticsIngestRequest(BaseModel):
    content_id: UUID
    views: int = Field(ge=0)
    likes: int = Field(ge=0)
    comments: int = Field(ge=0)
    # Optional client hint — server recalculates authoritative engagement_rate.
    engagement_rate: Decimal | None = None
    date: date

    @field_validator("date")
    @classmethod
    def date_not_in_far_future(cls, value: date) -> date:
        # Allow today + 1 day for timezone skew; reject absurd futures.
        from datetime import timedelta

        if value > date.today() + timedelta(days=1):
            raise ValueError("date cannot be more than one day in the future.")
        return value


class AnalyticsDailyPublic(BaseModel):
    id: UUID
    content_id: UUID
    views: int
    likes: int
    comments: int
    engagement_rate: float
    date: date
    created_at: datetime

    model_config = {"from_attributes": True}


class SeriesPoint(BaseModel):
    date: date
    views: int
    likes: int
    comments: int
    engagement_rate: float


class TopContentItem(BaseModel):
    content_id: UUID
    title: str
    trend_title: str | None = None
    views: int
    likes: int
    comments: int
    engagement_rate: float


class AnalyticsTotals(BaseModel):
    views: int
    likes: int
    comments: int
    average_engagement_rate: float
    content_with_metrics: int
    daily_rows: int


class ProjectAnalyticsSummary(BaseModel):
    project_id: UUID
    range_days: int
    totals: AnalyticsTotals
    series: list[SeriesPoint]
    top_content: list[TopContentItem]
    has_data: bool
    published_count: int = 0
    sync_error: str | None = None


class ContentAnalyticsSummary(BaseModel):
    content_id: UUID
    project_id: UUID
    totals: AnalyticsTotals
    series: list[SeriesPoint]
    has_data: bool


class CoachRecommendationPublic(BaseModel):
    title: str
    reason: str
    action: str
    priority: Literal["high", "medium", "low"]


class CoachResponse(BaseModel):
    project_id: UUID
    status: Literal["ready", "insufficient_data", "failed"]
    message: str | None = None
    analytics: dict | None = None
    recommendations: list[CoachRecommendationPublic] = []
    summary: str | None = None
    confidence: Literal["low", "medium", "high"] | None = None


class AnalyticsSyncResult(BaseModel):
    synced: int
    published: int
    skipped: bool = False
    cleared: int = 0
    message: str
