"""extend content for video-first; trends.language English filter

Revision ID: 20260812_0008
Revises: 20260812_0007
Create Date: 2026-08-12 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260812_0008"
down_revision: Union[str, None] = "20260812_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "trends",
        sa.Column("language", sa.String(length=16), nullable=True),
    )
    op.create_index(op.f("ix_trends_language"), "trends", ["language"], unique=False)

    op.add_column(
        "content",
        sa.Column(
            "format",
            sa.String(length=16),
            nullable=False,
            server_default="short",
        ),
    )
    op.add_column(
        "content",
        sa.Column("generation_phase", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "content",
        sa.Column("video_plan", sa.JSON(), nullable=True),
    )
    op.add_column(
        "content",
        sa.Column("video_url", sa.String(length=2000), nullable=True),
    )
    op.add_column(
        "content",
        sa.Column("storage_key", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "content",
        sa.Column("thumbnail_url", sa.String(length=2000), nullable=True),
    )
    op.add_column(
        "content",
        sa.Column(
            "publish_status",
            sa.String(length=32),
            nullable=False,
            server_default="draft",
        ),
    )
    op.add_column(
        "content",
        sa.Column("youtube_video_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "content",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "youtube_credentials",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("channel_id", sa.String(length=128), nullable=True),
        sa.Column("channel_title", sa.String(length=255), nullable=True),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_youtube_credentials_user_id"),
    )
    op.create_index(
        op.f("ix_youtube_credentials_user_id"),
        "youtube_credentials",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_youtube_credentials_user_id"), table_name="youtube_credentials")
    op.drop_table("youtube_credentials")

    op.drop_column("content", "updated_at")
    op.drop_column("content", "youtube_video_id")
    op.drop_column("content", "publish_status")
    op.drop_column("content", "thumbnail_url")
    op.drop_column("content", "storage_key")
    op.drop_column("content", "video_url")
    op.drop_column("content", "video_plan")
    op.drop_column("content", "generation_phase")
    op.drop_column("content", "format")

    op.drop_index(op.f("ix_trends_language"), table_name="trends")
    op.drop_column("trends", "language")
