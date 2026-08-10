from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProjectPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    niche: str | None = None
    audience: str | None = None
    brand_voice: str | None = None
    created_at: datetime


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    niche: str | None = Field(default=None, max_length=255)
    audience: str | None = Field(default=None, max_length=500)
    brand_voice: str | None = Field(default=None, max_length=500)
