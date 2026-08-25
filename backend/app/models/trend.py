import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Trend(Base):
    __tablename__ = "trends"
    __table_args__ = (
        UniqueConstraint("project_id", "url", name="uq_trends_project_url"),
    )

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
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # ISO-ish language tag from English filter (`en` or `und`).
    language: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    # Raw signals kept for transparency/debugging of the score (not in the
    # original Master Plan schema, but scoring must be explainable per the
    # Project Constitution — never a black-box/random number).
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    project: Mapped["Project"] = relationship(back_populates="trends")  # noqa: F821
    content_items: Mapped[list["Content"]] = relationship(  # noqa: F821
        back_populates="trend",
        cascade="all, delete-orphan",
    )
