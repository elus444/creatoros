from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AutomationTrendCollectRequest(BaseModel):
    project_id: UUID
    query: str | None = Field(default=None, max_length=200)


class AutomationContentGenerateRequest(BaseModel):
    project_id: UUID
    # If omitted, automation selects the project's highest-scored trend.
    trend_id: UUID | None = None


class AutomationPublishRequest(BaseModel):
    content_id: UUID


class AutomationCoachRequest(BaseModel):
    range_days: Literal[7, 30, 90] = 30


class AutomationJobAccepted(BaseModel):
    success: bool = True
    job_id: str
    status: Literal["queued", "running", "completed", "failed", "started"]
    idempotent_replay: bool = False


class AutomationJobPublic(BaseModel):
    job_id: str
    kind: str
    status: Literal["queued", "running", "completed", "failed"]
    content_id: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class AutomationStatusPublic(BaseModel):
    automation_configured: bool
    recent_jobs: list[AutomationJobPublic]
