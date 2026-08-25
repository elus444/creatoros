import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AnalyticsDaily(Base):
    """One performance snapshot per content item per calendar day (M6)."""

    __tablename__ = "analytics_daily"
    __table_args__ = (
        UniqueConstraint("content_id", "date", name="uq_analytics_daily_content_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    content_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("content.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    likes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    engagement_rate: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False, default=0
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    content: Mapped["Content"] = relationship(back_populates="analytics_daily")  # noqa: F821
