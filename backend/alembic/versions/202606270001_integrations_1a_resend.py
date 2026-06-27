"""add tenant resend transactional integrations

Revision ID: 202606270001
Revises: 202606230001
Create Date: 2026-06-27 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202606270001"
down_revision = "202606230001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_integrations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("secrets_json_encrypted", sa.Text(), nullable=True),
        sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "provider", name="uq_tenant_integrations_tenant_provider"),
    )
    op.create_index("ix_tenant_integrations_tenant_id", "tenant_integrations", ["tenant_id"])
    op.create_index("ix_tenant_integrations_tenant_provider", "tenant_integrations", ["tenant_id", "provider"])

    op.create_table(
        "tenant_integration_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=True),
        sa.Column("resource_id", sa.String(length=80), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_tenant_integration_events_tenant_provider",
        "tenant_integration_events",
        ["tenant_id", "provider"],
    )
    op.create_index("ix_tenant_integration_events_created_at", "tenant_integration_events", ["created_at"])

    op.create_table(
        "tenant_email_configs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("sender_email", sa.String(length=255), nullable=False),
        sa.Column("sender_name", sa.String(length=120), nullable=True),
        sa.Column("reply_to", sa.String(length=255), nullable=True),
        sa.Column("default_domain", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "provider", name="uq_tenant_email_configs_tenant_provider"),
    )
    op.create_index("ix_tenant_email_configs_tenant_provider", "tenant_email_configs", ["tenant_id", "provider"])

    op.create_table(
        "tenant_email_templates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("template_key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("html_body", sa.Text(), nullable=False),
        sa.Column("text_body", sa.Text(), nullable=False),
        sa.Column("variables_schema", sa.JSON(), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("is_marketing", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "template_key", name="uq_tenant_email_templates_tenant_key"),
    )
    op.create_index("ix_tenant_email_templates_tenant_key", "tenant_email_templates", ["tenant_id", "template_key"])

    op.create_table(
        "tenant_email_assets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("uploaded_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("visibility", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tenant_email_assets_tenant_status", "tenant_email_assets", ["tenant_id", "status"])
    op.create_index("ix_tenant_email_assets_storage_key", "tenant_email_assets", ["storage_key"])

    op.create_table(
        "tenant_email_sends",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("lead_id", sa.String(length=36), sa.ForeignKey("crm_leads.id"), nullable=True),
        sa.Column("contact_id", sa.String(length=36), sa.ForeignKey("crm_contacts.id"), nullable=True),
        sa.Column("template_id", sa.String(length=36), sa.ForeignKey("tenant_email_templates.id"), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_email_id", sa.String(length=255), nullable=True),
        sa.Column("to_email", sa.String(length=255), nullable=False),
        sa.Column("from_email", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tenant_email_sends_tenant_lead", "tenant_email_sends", ["tenant_id", "lead_id"])
    op.create_index("ix_tenant_email_sends_tenant_status", "tenant_email_sends", ["tenant_id", "status"])
    op.create_index(
        "ix_tenant_email_sends_tenant_provider_email",
        "tenant_email_sends",
        ["tenant_id", "provider_email_id"],
    )
    op.create_index("ix_tenant_email_sends_tenant_created_at", "tenant_email_sends", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_tenant_email_sends_tenant_created_at", table_name="tenant_email_sends")
    op.drop_index("ix_tenant_email_sends_tenant_provider_email", table_name="tenant_email_sends")
    op.drop_index("ix_tenant_email_sends_tenant_status", table_name="tenant_email_sends")
    op.drop_index("ix_tenant_email_sends_tenant_lead", table_name="tenant_email_sends")
    op.drop_table("tenant_email_sends")
    op.drop_index("ix_tenant_email_assets_storage_key", table_name="tenant_email_assets")
    op.drop_index("ix_tenant_email_assets_tenant_status", table_name="tenant_email_assets")
    op.drop_table("tenant_email_assets")
    op.drop_index("ix_tenant_email_templates_tenant_key", table_name="tenant_email_templates")
    op.drop_table("tenant_email_templates")
    op.drop_index("ix_tenant_email_configs_tenant_provider", table_name="tenant_email_configs")
    op.drop_table("tenant_email_configs")
    op.drop_index("ix_tenant_integration_events_created_at", table_name="tenant_integration_events")
    op.drop_index("ix_tenant_integration_events_tenant_provider", table_name="tenant_integration_events")
    op.drop_table("tenant_integration_events")
    op.drop_index("ix_tenant_integrations_tenant_provider", table_name="tenant_integrations")
    op.drop_index("ix_tenant_integrations_tenant_id", table_name="tenant_integrations")
    op.drop_table("tenant_integrations")
