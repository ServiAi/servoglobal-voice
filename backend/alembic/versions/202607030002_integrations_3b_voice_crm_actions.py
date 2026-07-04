"""integrations 3b voice crm actions

Revision ID: 202607030002
Revises: 202607010001
Create Date: 2026-07-03 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "202607030002"
down_revision = "202607030001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. tenant_voice_provider_configs
    op.create_table(
        "tenant_voice_provider_configs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("base_url", sa.String(length=255), nullable=True),
        sa.Column("default_voice_agent_id", sa.String(length=120), nullable=True),
        sa.Column("default_from_number", sa.String(length=80), nullable=True),
        sa.Column("default_language", sa.String(length=16), nullable=False),
        sa.Column("default_timezone", sa.String(length=80), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("webhook_secret_encrypted", sa.Text(), nullable=True),
        sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "provider", name="uq_tenant_voice_provider_configs_tenant_provider"),
    )
    op.create_index(
        "ix_tenant_voice_provider_configs_tenant_provider",
        "tenant_voice_provider_configs",
        ["tenant_id", "provider"],
    )
    op.create_index(
        "ix_tenant_voice_provider_configs_tenant_status",
        "tenant_voice_provider_configs",
        ["tenant_id", "status"],
    )

    # 2. tenant_voice_agent_configs
    op.create_table(
        "tenant_voice_agent_configs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("provider_config_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_agent_id", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("purpose", sa.String(length=80), nullable=False),
        sa.Column("default_language", sa.String(length=16), nullable=False),
        sa.Column("default_timezone", sa.String(length=80), nullable=False),
        sa.Column("default_voice", sa.String(length=80), nullable=True),
        sa.Column("default_system_prompt", sa.Text(), nullable=True),
        sa.Column("default_tools_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["provider_config_id"], ["tenant_voice_provider_configs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "provider_agent_id", name="uq_tenant_voice_agent_configs_tenant_agent"),
    )
    op.create_index(
        "ix_tenant_voice_agent_configs_tenant_agent",
        "tenant_voice_agent_configs",
        ["tenant_id", "provider_agent_id"],
    )
    op.create_index(
        "ix_tenant_voice_agent_configs_tenant_status",
        "tenant_voice_agent_configs",
        ["tenant_id", "status"],
    )

    # 3. crm_voice_calls
    op.create_table(
        "crm_voice_calls",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("lead_id", sa.String(length=36), nullable=True),
        sa.Column("contact_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_call_id", sa.String(length=255), nullable=True),
        sa.Column("provider_session_id", sa.String(length=255), nullable=True),
        sa.Column("provider_agent_id", sa.String(length=255), nullable=True),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("to_phone", sa.String(length=80), nullable=True),
        sa.Column("from_number", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("recording_url", sa.Text(), nullable=True),
        sa.Column("transcript_url", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["crm_leads.id"]),
        sa.ForeignKeyConstraint(["contact_id"], ["crm_contacts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_crm_voice_calls_tenant_lead",
        "crm_voice_calls",
        ["tenant_id", "lead_id"],
    )
    op.create_index(
        "ix_crm_voice_calls_tenant_contact",
        "crm_voice_calls",
        ["tenant_id", "contact_id"],
    )
    op.create_index(
        "ix_crm_voice_calls_tenant_status",
        "crm_voice_calls",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_crm_voice_calls_provider_call",
        "crm_voice_calls",
        ["provider", "provider_call_id"],
    )

    # 4. crm_voice_call_events
    op.create_table(
        "crm_voice_call_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("voice_call_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload_summary_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["voice_call_id"], ["crm_voice_calls.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_crm_voice_call_events_tenant_call",
        "crm_voice_call_events",
        ["tenant_id", "voice_call_id"],
    )
    op.create_index(
        "ix_crm_voice_call_events_event_type",
        "crm_voice_call_events",
        ["event_type"],
    )


def downgrade() -> None:
    op.drop_table("crm_voice_call_events")
    op.drop_table("crm_voice_calls")
    op.drop_table("tenant_voice_agent_configs")
    op.drop_table("tenant_voice_provider_configs")
