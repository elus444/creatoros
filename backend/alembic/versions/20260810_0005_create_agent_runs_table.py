"""create agent_runs table

Revision ID: 20260810_0005
Revises: 20260810_0004
Create Date: 2026-08-10 00:05:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_0005"
down_revision: Union[str, None] = "20260810_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("content_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("agent_name", sa.String(length=50), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("tokens", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["content_id"], ["content.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_runs_content_id"), "agent_runs", ["content_id"], unique=False
    )
    op.create_index(
        op.f("ix_agent_runs_agent_name"), "agent_runs", ["agent_name"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_runs_agent_name"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_content_id"), table_name="agent_runs")
    op.drop_table("agent_runs")
