"""integrations 2a calcom google calendar foundation

Revision ID: 202607010001
Revises: 202606300001
Create Date: 2026-07-01 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202607010001"
down_revision = "202606300001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_booking_configs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("calendar_mode", sa.String(length=40), nullable=False),
        sa.Column("cal_api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("cal_api_version", sa.String(length=40), nullable=False),
        sa.Column("organization_slug", sa.String(length=120), nullable=True),
        sa.Column("default_event_type_id", sa.Integer(), nullable=True),
        sa.Column("default_event_type_slug", sa.String(length=160), nullable=True),
        sa.Column("default_username", sa.String(length=160), nullable=True),
        sa.Column("default_team_slug", sa.String(length=160), nullable=True),
        sa.Column("default_timezone", sa.String(length=80), nullable=False),
        sa.Column("default_language", sa.String(length=16), nullable=False),
        sa.Column("default_location_type", sa.String(length=80), nullable=True),
        sa.Column("default_length_minutes", sa.Integer(), nullable=False),
        sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "provider", name="uq_tenant_booking_configs_tenant_provider"),
    )
    op.create_index("ix_tenant_booking_configs_tenant_provider", "tenant_booking_configs", ["tenant_id", "provider"])
    op.create_index("ix_tenant_booking_configs_tenant_status", "tenant_booking_configs", ["tenant_id", "status"])

    op.create_table(
        "tenant_google_calendar_connections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("google_account_email", sa.String(length=255), nullable=True),
        sa.Column("calendar_id", sa.String(length=255), nullable=False),
        sa.Column("calendar_summary", sa.String(length=255), nullable=True),
        sa.Column("access_token_encrypted", sa.Text(), nullable=True),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes_json", sa.JSON(), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_tenant_google_calendar_connections_tenant_status",
        "tenant_google_calendar_connections",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_tenant_google_calendar_connections_tenant_user",
        "tenant_google_calendar_connections",
        ["tenant_id", "user_id"],
    )

    op.create_table(
        "tenant_voice_booking_configs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("provider_agent_id", sa.String(length=255), nullable=True),
        sa.Column("agent_name", sa.String(length=255), nullable=True),
        sa.Column("default_booking_config_id", sa.String(length=36), sa.ForeignKey("tenant_booking_configs.id"), nullable=True),
        sa.Column("default_event_type_id", sa.Integer(), nullable=True),
        sa.Column("default_event_type_slug", sa.String(length=160), nullable=True),
        sa.Column("default_timezone", sa.String(length=80), nullable=False),
        sa.Column("default_jornada_rules_json", sa.JSON(), nullable=False),
        sa.Column("enabled_tools_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tenant_voice_booking_configs_tenant_agent", "tenant_voice_booking_configs", ["tenant_id", "provider_agent_id"])
    op.create_index("ix_tenant_voice_booking_configs_tenant_status", "tenant_voice_booking_configs", ["tenant_id", "status"])

    op.create_table(
        "crm_bookings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("lead_id", sa.String(length=36), sa.ForeignKey("crm_leads.id"), nullable=True),
        sa.Column("contact_id", sa.String(length=36), sa.ForeignKey("crm_contacts.id"), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_booking_id", sa.String(length=255), nullable=True),
        sa.Column("provider_booking_uid", sa.String(length=255), nullable=True),
        sa.Column("provider_event_type_id", sa.String(length=80), nullable=True),
        sa.Column("provider_event_type_slug", sa.String(length=160), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timezone", sa.String(length=80), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("meeting_url", sa.String(length=500), nullable=True),
        sa.Column("location_type", sa.String(length=80), nullable=True),
        sa.Column("attendee_name", sa.String(length=255), nullable=False),
        sa.Column("attendee_email", sa.String(length=255), nullable=False),
        sa.Column("attendee_phone", sa.String(length=80), nullable=True),
        sa.Column("host_name", sa.String(length=255), nullable=True),
        sa.Column("host_email", sa.String(length=255), nullable=True),
        sa.Column("google_calendar_event_id", sa.String(length=255), nullable=True),
        sa.Column("calendar_mode", sa.String(length=40), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rescheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name, cols in {
        "ix_crm_bookings_tenant_lead": ["tenant_id", "lead_id"],
        "ix_crm_bookings_tenant_contact": ["tenant_id", "contact_id"],
        "ix_crm_bookings_tenant_provider_uid": ["tenant_id", "provider_booking_uid"],
        "ix_crm_bookings_tenant_status": ["tenant_id", "status"],
        "ix_crm_bookings_tenant_start": ["tenant_id", "start_at"],
        "ix_crm_bookings_tenant_google_event": ["tenant_id", "google_calendar_event_id"],
    }.items():
        op.create_index(name, "crm_bookings", cols)

    op.create_table(
        "crm_booking_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("booking_id", sa.String(length=36), sa.ForeignKey("crm_bookings.id"), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload_summary_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_crm_booking_events_tenant_booking", "crm_booking_events", ["tenant_id", "booking_id"])
    op.create_index("ix_crm_booking_events_tenant_provider", "crm_booking_events", ["tenant_id", "provider"])
    op.create_index("ix_crm_booking_events_created_at", "crm_booking_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_crm_booking_events_created_at", table_name="crm_booking_events")
    op.drop_index("ix_crm_booking_events_tenant_provider", table_name="crm_booking_events")
    op.drop_index("ix_crm_booking_events_tenant_booking", table_name="crm_booking_events")
    op.drop_table("crm_booking_events")
    for name in [
        "ix_crm_bookings_tenant_google_event",
        "ix_crm_bookings_tenant_start",
        "ix_crm_bookings_tenant_status",
        "ix_crm_bookings_tenant_provider_uid",
        "ix_crm_bookings_tenant_contact",
        "ix_crm_bookings_tenant_lead",
    ]:
        op.drop_index(name, table_name="crm_bookings")
    op.drop_table("crm_bookings")
    op.drop_index("ix_tenant_voice_booking_configs_tenant_status", table_name="tenant_voice_booking_configs")
    op.drop_index("ix_tenant_voice_booking_configs_tenant_agent", table_name="tenant_voice_booking_configs")
    op.drop_table("tenant_voice_booking_configs")
    op.drop_index("ix_tenant_google_calendar_connections_tenant_user", table_name="tenant_google_calendar_connections")
    op.drop_index("ix_tenant_google_calendar_connections_tenant_status", table_name="tenant_google_calendar_connections")
    op.drop_table("tenant_google_calendar_connections")
    op.drop_index("ix_tenant_booking_configs_tenant_status", table_name="tenant_booking_configs")
    op.drop_index("ix_tenant_booking_configs_tenant_provider", table_name="tenant_booking_configs")
    op.drop_table("tenant_booking_configs")
