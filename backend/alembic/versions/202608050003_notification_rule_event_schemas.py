"""add notification rule event schema metadata

Revision ID: 202608050003
Revises: 202608050002
"""

import sqlalchemy as sa

from alembic import op


revision = "202608050003"
down_revision = "202608050002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenant_notification_rules",
        sa.Column("conditions_mode", sa.String(length=8), nullable=False, server_default="all"),
    )
    op.add_column(
        "tenant_notification_rules",
        sa.Column("event_schema_version", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("tenant_notification_rules", "event_schema_version")
    op.drop_column("tenant_notification_rules", "conditions_mode")
