import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    niche: Mapped[str | None] = mapped_column(String(255), nullable=True)
    audience: Mapped[str | None] = mapped_column(String(500), nullable=True)
    brand_voice: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="projects")  # noqa: F821
    trends: Mapped[list["Trend"]] = relationship(  # noqa: F821
        back_populates="project",
        cascade="all, delete-orphan",
    )
    content_items: Mapped[list["Content"]] = relationship(  # noqa: F821
        back_populates="project",
        cascade="all, delete-orphan",
    )
