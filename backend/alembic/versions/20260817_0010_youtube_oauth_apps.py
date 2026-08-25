"""add per-user Google OAuth client credentials for YouTube connect

Revision ID: 20260817_0010
Revises: 20260817_0009
Create Date: 2026-08-17 12:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260817_0010"
down_revision: Union[str, None] = "20260817_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "youtube_oauth_apps",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("client_secret_encrypted", sa.Text(), nullable=False),
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
        sa.UniqueConstraint("user_id", name="uq_youtube_oauth_apps_user_id"),
    )
    op.create_index(
        op.f("ix_youtube_oauth_apps_user_id"),
        "youtube_oauth_apps",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_youtube_oauth_apps_user_id"), table_name="youtube_oauth_apps")
    op.drop_table("youtube_oauth_apps")
