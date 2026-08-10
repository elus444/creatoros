"""create content table

Revision ID: 20260810_0004
Revises: 20260810_0003
Create Date: 2026-08-10 00:04:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_0004"
down_revision: Union[str, None] = "20260810_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "content",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("trend_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("research", sa.JSON(), nullable=True),
        sa.Column("strategy", sa.JSON(), nullable=True),
        sa.Column("script", sa.Text(), nullable=True),
        sa.Column("titles", sa.JSON(), nullable=True),
        sa.Column("captions", sa.Text(), nullable=True),
        sa.Column("hashtags", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trend_id"], ["trends.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_content_project_id"), "content", ["project_id"], unique=False)
    op.create_index(op.f("ix_content_trend_id"), "content", ["trend_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_content_trend_id"), table_name="content")
    op.drop_index(op.f("ix_content_project_id"), table_name="content")
    op.drop_table("content")
