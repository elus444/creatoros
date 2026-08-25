"""add YouTube channel thumbnail on stored OAuth credentials

Revision ID: 20260817_0009
Revises: 20260812_0008
Create Date: 2026-08-17 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260817_0009"
down_revision: Union[str, None] = "20260812_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "youtube_credentials",
        sa.Column("channel_thumbnail_url", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("youtube_credentials", "channel_thumbnail_url")
