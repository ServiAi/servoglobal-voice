"""integrations 3a whatsapp crm actions

Revision ID: 202607030001
Revises: 202607010001
Create Date: 2026-07-03 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202607030001"
down_revision = "202607010001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_whatsapp_configs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("phone_number_id", sa.String(length=120), nullable=False),
        sa.Column("business_account_id", sa.String(length=120), nullable=True),
        sa.Column("display_phone_number", sa.String(length=80), nullable=True),
        sa.Column("default_language", sa.String(length=16), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=True),
        sa.Column("webhook_verify_token_encrypted", sa.Text(), nullable=True),
        sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "provider", name="uq_tenant_whatsapp_configs_tenant_provider"),
    )
    op.create_index("ix_tenant_whatsapp_configs_tenant_provider", "tenant_whatsapp_configs", ["tenant_id", "provider"])
    op.create_index("ix_tenant_whatsapp_configs_tenant_status", "tenant_whatsapp_configs", ["tenant_id", "status"])
    op.create_index("ix_tenant_whatsapp_configs_phone_number", "tenant_whatsapp_configs", ["phone_number_id"])

    op.create_table(
        "tenant_whatsapp_templates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("template_key", sa.String(length=80), nullable=False),
        sa.Column("provider_template_name", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("variables_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "template_key", name="uq_tenant_whatsapp_templates_tenant_key"),
    )
    op.create_index("ix_tenant_whatsapp_templates_tenant_key", "tenant_whatsapp_templates", ["tenant_id", "template_key"])
    op.create_index("ix_tenant_whatsapp_templates_tenant_status", "tenant_whatsapp_templates", ["tenant_id", "status"])

    op.create_table(
        "crm_whatsapp_messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("lead_id", sa.String(length=36), sa.ForeignKey("crm_leads.id"), nullable=True),
        sa.Column("contact_id", sa.String(length=36), sa.ForeignKey("crm_contacts.id"), nullable=True),
        sa.Column("template_id", sa.String(length=36), sa.ForeignKey("tenant_whatsapp_templates.id"), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("to_phone", sa.String(length=80), nullable=True),
        sa.Column("from_phone", sa.String(length=80), nullable=True),
        sa.Column("template_key", sa.String(length=80), nullable=True),
        sa.Column("message_preview", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_crm_whatsapp_messages_tenant_lead", "crm_whatsapp_messages", ["tenant_id", "lead_id"])
    op.create_index("ix_crm_whatsapp_messages_tenant_contact", "crm_whatsapp_messages", ["tenant_id", "contact_id"])
    op.create_index("ix_crm_whatsapp_messages_tenant_status", "crm_whatsapp_messages", ["tenant_id", "status"])
    op.create_index(
        "ix_crm_whatsapp_messages_tenant_provider_message",
        "crm_whatsapp_messages",
        ["tenant_id", "provider_message_id"],
    )
    op.create_index("ix_crm_whatsapp_messages_tenant_created_at", "crm_whatsapp_messages", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_crm_whatsapp_messages_tenant_created_at", table_name="crm_whatsapp_messages")
    op.drop_index("ix_crm_whatsapp_messages_tenant_provider_message", table_name="crm_whatsapp_messages")
    op.drop_index("ix_crm_whatsapp_messages_tenant_status", table_name="crm_whatsapp_messages")
    op.drop_index("ix_crm_whatsapp_messages_tenant_contact", table_name="crm_whatsapp_messages")
    op.drop_index("ix_crm_whatsapp_messages_tenant_lead", table_name="crm_whatsapp_messages")
    op.drop_table("crm_whatsapp_messages")

    op.drop_index("ix_tenant_whatsapp_templates_tenant_status", table_name="tenant_whatsapp_templates")
    op.drop_index("ix_tenant_whatsapp_templates_tenant_key", table_name="tenant_whatsapp_templates")
    op.drop_table("tenant_whatsapp_templates")

    op.drop_index("ix_tenant_whatsapp_configs_phone_number", table_name="tenant_whatsapp_configs")
    op.drop_index("ix_tenant_whatsapp_configs_tenant_status", table_name="tenant_whatsapp_configs")
    op.drop_index("ix_tenant_whatsapp_configs_tenant_provider", table_name="tenant_whatsapp_configs")
    op.drop_table("tenant_whatsapp_configs")
