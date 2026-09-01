"""chatwoot multitenant v1

Revision ID: 202609010001
Revises: 202608310002
Create Date: 2026-09-01 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202609010001"
down_revision = "202608310002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_chatwoot_configs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("default_inbox_id", sa.Integer(), nullable=True),
        sa.Column("api_token_encrypted", sa.Text(), nullable=True),
        sa.Column("webhook_key", sa.String(length=64), nullable=False),
        sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "provider", name="uq_tenant_chatwoot_configs_tenant_provider"),
        sa.UniqueConstraint("webhook_key", name="uq_tenant_chatwoot_configs_webhook_key"),
    )
    op.create_index(
        "ix_tenant_chatwoot_configs_tenant_provider", "tenant_chatwoot_configs", ["tenant_id", "provider"]
    )
    op.create_index(
        "ix_tenant_chatwoot_configs_tenant_status", "tenant_chatwoot_configs", ["tenant_id", "status"]
    )
    op.create_index(
        "ix_tenant_chatwoot_configs_account_id", "tenant_chatwoot_configs", ["account_id"]
    )

    op.create_table(
        "tenant_chatwoot_inboxes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "chatwoot_config_id",
            sa.String(length=36),
            sa.ForeignKey("tenant_chatwoot_configs.id"),
            nullable=False,
        ),
        sa.Column("chatwoot_inbox_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=80), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_tenant_chatwoot_inboxes_tenant_config", "tenant_chatwoot_inboxes", ["tenant_id", "chatwoot_config_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_chatwoot_inboxes_tenant_config", table_name="tenant_chatwoot_inboxes")
    op.drop_table("tenant_chatwoot_inboxes")

    op.drop_index("ix_tenant_chatwoot_configs_account_id", table_name="tenant_chatwoot_configs")
    op.drop_index("ix_tenant_chatwoot_configs_tenant_status", table_name="tenant_chatwoot_configs")
    op.drop_index("ix_tenant_chatwoot_configs_tenant_provider", table_name="tenant_chatwoot_configs")
    op.drop_table("tenant_chatwoot_configs")
