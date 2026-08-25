import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ContentStatus:
    """Content lifecycle (video-first product).

    PENDING → GENERATED → REVIEW → APPROVED → EXPORTED
             ↘ FAILED

    GENERATED means a real video asset is ready for review (video_url set),
    or the pipeline finished with a durable failure recorded on `error`.
    Publish to YouTube uses `publish_status` separately from editorial status.
    """

    PENDING = "PENDING"
    GENERATED = "GENERATED"
    FAILED = "FAILED"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    EXPORTED = "EXPORTED"


class ContentFormat:
    """Creator OS is short-form YouTube Shorts only (9:16)."""

    SHORT = "short"


class PublishStatus:
    DRAFT = "draft"
    READY = "ready"
    UPLOADING = "uploading"
    PUBLISHED = "published"
    FAILED = "failed"


class GenerationPhase:
    QUEUED = "queued"
    RESEARCHING = "researching"
    PLANNING = "planning"
    GENERATING_VIDEO = "generating_video"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Content(Base):
    __tablename__ = "content"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trend_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("trends.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    format: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ContentFormat.SHORT
    )
    generation_phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Structured agent outputs (validated Pydantic schemas serialized to JSON).
    research: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Planning Agent output (historically named strategy).
    strategy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    video_plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Narration / voiceover text produced as part of the video plan (not the
    # primary product output — the video file is).
    script: Mapped[str | None] = mapped_column(Text, nullable=True)
    titles: Mapped[list | None] = mapped_column(JSON, nullable=True)
    captions: Mapped[str | None] = mapped_column(Text, nullable=True)
    hashtags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    publish_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PublishStatus.DRAFT
    )
    youtube_video_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ContentStatus.PENDING
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    project: Mapped["Project"] = relationship(back_populates="content_items")  # noqa: F821
    trend: Mapped["Trend"] = relationship(back_populates="content_items")  # noqa: F821
    agent_runs: Mapped[list["AgentRun"]] = relationship(  # noqa: F821
        back_populates="content",
        cascade="all, delete-orphan",
        order_by="AgentRun.created_at",
    )
    analytics_daily: Mapped[list["AnalyticsDaily"]] = relationship(  # noqa: F821
        back_populates="content",
        cascade="all, delete-orphan",
        order_by="AnalyticsDaily.date",
    )
