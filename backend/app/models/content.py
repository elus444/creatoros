import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ContentStatus:
    """String status values for `Content.status` (Constitution: agents/DB use
    plain strings, not a native DB enum, matching the `Trend.source` style).

    M3 produces PENDING → GENERATED or FAILED. M4 owns the workspace flow
    GENERATED → REVIEW → APPROVED → EXPORTED.
    """

    PENDING = "PENDING"
    GENERATED = "GENERATED"
    FAILED = "FAILED"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    EXPORTED = "EXPORTED"


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
    # Structured agent outputs (validated Pydantic schemas serialized to JSON
    # — never raw/unvalidated LLM text, per Constitution §6).
    research: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    strategy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    script: Mapped[str | None] = mapped_column(Text, nullable=True)
    titles: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Master Plan schema names this column "captions" (plural); the Content
    # Agent produces a single caption, stored as text under that column name.
    captions: Mapped[str | None] = mapped_column(Text, nullable=True)
    hashtags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ContentStatus.PENDING
    )
    # Not in the original Master Plan schema, but required to honestly
    # surface *why* generation failed (Constitution §22: never swallow
    # errors) rather than leaving a silent FAILED row with no explanation —
    # same justification as Trend.metrics being added beyond the base schema.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    project: Mapped["Project"] = relationship(back_populates="content_items")  # noqa: F821
    trend: Mapped["Trend"] = relationship(back_populates="content_items")  # noqa: F821
    agent_runs: Mapped[list["AgentRun"]] = relationship(  # noqa: F821
        back_populates="content",
        cascade="all, delete-orphan",
        order_by="AgentRun.created_at",
    )
