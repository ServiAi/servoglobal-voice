"""chatwoot managed mode

Revision ID: 202609020001
Revises: 202609010001
Create Date: 2026-09-02 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202609020001"
down_revision = "202609010001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenant_chatwoot_configs",
        sa.Column("mode", sa.String(length=20), nullable=False, server_default="external"),
    )
    op.add_column(
        "tenant_chatwoot_configs",
        sa.Column("platform_agent_bot_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenant_chatwoot_configs", "platform_agent_bot_id")
    op.drop_column("tenant_chatwoot_configs", "mode")
