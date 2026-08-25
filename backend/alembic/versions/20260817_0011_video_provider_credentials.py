"""per-user encrypted video provider credentials

Revision ID: 20260817_0011
Revises: 20260817_0010
Create Date: 2026-08-17 13:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260817_0011"
down_revision: Union[str, None] = "20260817_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "video_provider_credentials",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model_id", sa.String(length=200), nullable=True),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
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
        sa.UniqueConstraint("user_id", name="uq_video_provider_credentials_user_id"),
    )
    op.create_index(
        op.f("ix_video_provider_credentials_user_id"),
        "video_provider_credentials",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_video_provider_credentials_user_id"),
        table_name="video_provider_credentials",
    )
    op.drop_table("video_provider_credentials")
