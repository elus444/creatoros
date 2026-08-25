import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AgentRunStatus:
    SUCCESS = "success"
    FAILED = "failed"


class AgentRun(Base):
    """One row per agent execution *attempt* (Constitution §8: every AI
    execution must be observable). Retries are logged as separate rows
    (see `attempt`) so malformed-output retry behavior is fully visible,
    not just the final outcome.
    """

    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    # Nullable for project-scoped Analytics/Coach runs (M6). Content-scoped
    # agents (research/strategy/content/suggestion) still set content_id.
    content_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("content.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Not in the original Master Plan schema; distinguishes retry attempts
    # for the same agent within one pipeline run.
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    input: Mapped[dict] = mapped_column(JSON, nullable=False)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # Not in the original Master Plan schema; required so a failed attempt
    # is honestly explained rather than a bare "failed" status.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # {"prompt": int, "completion": int, "total": int} when the provider
    # reports usage; never fabricated when unavailable (Constitution §8).
    tokens: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    content: Mapped["Content"] = relationship(back_populates="agent_runs")  # noqa: F821
