"""crm call context and unique lead per call

Revision ID: 202606220001
Revises: 202606180001
Create Date: 2026-06-22 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "202606220001"
down_revision = "202606180001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_crm_leads_tenant_created_call_unique",
        "crm_leads",
        ["tenant_id", "created_from_call_id"],
        unique=True,
        postgresql_where=sa.text("created_from_call_id IS NOT NULL"),
        sqlite_where=sa.text("created_from_call_id IS NOT NULL"),
    )

    op.create_table(
        "crm_call_contexts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_provider", sa.String(80), nullable=False),
        sa.Column("external_call_id", sa.String(255), nullable=True),
        sa.Column("form_submission_id", sa.String(255), nullable=True),
        sa.Column("context_id", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(80), nullable=True),
        sa.Column("phone_normalized", sa.String(80), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("interest", sa.String(255), nullable=True),
        sa.Column("industry", sa.String(255), nullable=True),
        sa.Column("use_case", sa.String(255), nullable=True),
        sa.Column("volume", sa.String(255), nullable=True),
        sa.Column("pain_point", sa.Text(), nullable=True),
        sa.Column("budget_range", sa.String(255), nullable=True),
        sa.Column("intent_level", sa.String(80), nullable=True),
        sa.Column("source", sa.String(120), nullable=True),
        sa.Column("campaign", sa.String(120), nullable=True),
        sa.Column("utm_source", sa.String(120), nullable=True),
        sa.Column("utm_campaign", sa.String(120), nullable=True),
        sa.Column("raw_context_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_crm_call_contexts_tenant_provider_call",
        "crm_call_contexts",
        ["tenant_id", "external_provider", "external_call_id"],
    )
    op.create_index(
        "ix_crm_call_contexts_tenant_form_submission",
        "crm_call_contexts",
        ["tenant_id", "form_submission_id"],
    )
    op.create_index(
        "ix_crm_call_contexts_tenant_context",
        "crm_call_contexts",
        ["tenant_id", "context_id"],
    )
    op.create_index(
        "ix_crm_call_contexts_tenant_phone",
        "crm_call_contexts",
        ["tenant_id", "phone_normalized"],
    )
    op.create_index(
        "ix_crm_call_contexts_tenant_created_at",
        "crm_call_contexts",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_crm_call_contexts_tenant_created_at", table_name="crm_call_contexts")
    op.drop_index("ix_crm_call_contexts_tenant_phone", table_name="crm_call_contexts")
    op.drop_index("ix_crm_call_contexts_tenant_context", table_name="crm_call_contexts")
    op.drop_index("ix_crm_call_contexts_tenant_form_submission", table_name="crm_call_contexts")
    op.drop_index("ix_crm_call_contexts_tenant_provider_call", table_name="crm_call_contexts")
    op.drop_table("crm_call_contexts")
    op.drop_index("ix_crm_leads_tenant_created_call_unique", table_name="crm_leads")
