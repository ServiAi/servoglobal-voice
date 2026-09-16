"""Store the runtime channel on projected analytics calls.

Revision ID: 202609150001
Revises: 202609140002
"""

import sqlalchemy as sa
from alembic import op

revision = "202609150001"
down_revision = "202609140002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calls", sa.Column("channel", sa.String(24), nullable=True))


def downgrade() -> None:
    op.drop_column("calls", "channel")
