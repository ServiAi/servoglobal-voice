"""chatwoot display names

Revision ID: 202609020002
Revises: 202609020001
Create Date: 2026-09-02 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202609020002"
down_revision = "202609020001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenant_chatwoot_configs",
        sa.Column("account_name", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "tenant_chatwoot_configs",
        sa.Column("default_inbox_name", sa.String(length=160), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenant_chatwoot_configs", "default_inbox_name")
    op.drop_column("tenant_chatwoot_configs", "account_name")
