"""prevent duplicate project trends and backfill agent run project IDs

Revision ID: 20260812_0007
Revises: 20260812_0006
Create Date: 2026-08-12 00:07:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260812_0007"
down_revision: Union[str, None] = "20260812_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing content-scoped attempts predate agent_runs.project_id. Backfill
    # their owning project so all agent activity remains project-queryable.
    op.execute(
        """
        UPDATE agent_runs
        SET project_id = (
            SELECT content.project_id
            FROM content
            WHERE content.id = agent_runs.content_id
        )
        WHERE content_id IS NOT NULL AND project_id IS NULL
        """
    )
    op.create_unique_constraint("uq_trends_project_url", "trends", ["project_id", "url"])


def downgrade() -> None:
    op.drop_constraint("uq_trends_project_url", "trends", type_="unique")
