"""create analytics_daily; allow project-scoped agent_runs

Revision ID: 20260812_0006
Revises: 20260810_0005
Create Date: 2026-08-12 00:06:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260812_0006"
down_revision: Union[str, None] = "20260810_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analytics_daily",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("content_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("likes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("comments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "engagement_rate",
            sa.Numeric(precision=8, scale=4),
            nullable=False,
            server_default="0",
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["content_id"], ["content.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "content_id", "date", name="uq_analytics_daily_content_date"
        ),
    )
    op.create_index(
        op.f("ix_analytics_daily_content_id"),
        "analytics_daily",
        ["content_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_analytics_daily_date"), "analytics_daily", ["date"], unique=False
    )

    # Project-scoped Analytics/Coach agent runs (content_id optional).
    op.add_column(
        "agent_runs",
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_runs_project_id_projects",
        "agent_runs",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_agent_runs_project_id"), "agent_runs", ["project_id"], unique=False
    )
    op.alter_column(
        "agent_runs",
        "content_id",
        existing_type=sa.Uuid(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    # Restore content_id NOT NULL only if every row still has a content_id.
    op.execute("DELETE FROM agent_runs WHERE content_id IS NULL")
    op.alter_column(
        "agent_runs",
        "content_id",
        existing_type=sa.Uuid(as_uuid=True),
        nullable=False,
    )
    op.drop_index(op.f("ix_agent_runs_project_id"), table_name="agent_runs")
    op.drop_constraint(
        "fk_agent_runs_project_id_projects", "agent_runs", type_="foreignkey"
    )
    op.drop_column("agent_runs", "project_id")

    op.drop_index(op.f("ix_analytics_daily_date"), table_name="analytics_daily")
    op.drop_index(op.f("ix_analytics_daily_content_id"), table_name="analytics_daily")
    op.drop_table("analytics_daily")
