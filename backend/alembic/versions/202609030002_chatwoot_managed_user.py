"""chatwoot managed user columns

Revision ID: 202609030002
Revises: 202609030001
Create Date: 2026-09-03 01:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202609030002"
down_revision = "202609030001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenant_chatwoot_configs",
        sa.Column("managed_user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "tenant_chatwoot_configs",
        sa.Column("managed_user_email", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenant_chatwoot_configs", "managed_user_email")
    op.drop_column("tenant_chatwoot_configs", "managed_user_id")
