"""add tenant integration availability

Revision ID: 202607230001
Revises: 202607030002
"""

from alembic import op
import sqlalchemy as sa


revision = "202607230001"
down_revision = "202607030002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenant_integrations",
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("tenant_integrations", "enabled")
