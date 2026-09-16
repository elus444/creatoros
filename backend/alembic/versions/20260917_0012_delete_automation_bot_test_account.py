"""delete automation-bot test account created while wiring up n8n

Removes the throwaway test user (automation-bot@creatoros.app) and its
"n8n Automation Demo" project created to validate the n8n <-> creatoros
automation loop end-to-end. All FKs from projects/trends/content/etc.
back to users are ON DELETE CASCADE, so deleting the user row is enough
to remove everything it owns.

This is a one-off data cleanup, not a schema change -- downgrade is a
deliberate no-op since the deleted rows cannot be reconstructed.

Revision ID: 20260917_0012
Revises: 20260817_0011
Create Date: 2026-09-17 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260917_0012"
down_revision: Union[str, None] = "20260817_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM users WHERE email = 'automation-bot@creatoros.app'"
        )
    )


def downgrade() -> None:
    # Deliberate no-op: the deleted test user/project/trends/content rows
    # cannot be reconstructed, and there is nothing else to reverse.
    pass
