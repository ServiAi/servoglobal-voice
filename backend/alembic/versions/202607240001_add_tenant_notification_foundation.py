"""add tenant notification foundation

Revision ID: 202607240001
Revises: 202607230001
"""

from alembic import op
import sqlalchemy as sa


revision = "202607240001"
down_revision = "202607230001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_capabilities",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("capability_key", sa.String(length=80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "capability_key", name="uq_tenant_capabilities_tenant_capability_key"),
    )
    op.create_index(
        "ix_tenant_capabilities_tenant_enabled", "tenant_capabilities", ["tenant_id", "enabled"]
    )
    op.create_index(
        "ix_tenant_capabilities_tenant_capability_key",
        "tenant_capabilities",
        ["tenant_id", "capability_key"],
    )

    op.create_table(
        "tenant_notification_recipients",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("group_key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("destination", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "group_key",
            "channel",
            "destination",
            name="uq_tenant_notification_recipients_tenant_group_channel_destination",
        ),
    )
    op.create_index(
        "ix_tenant_notification_recipients_tenant_group_status",
        "tenant_notification_recipients",
        ["tenant_id", "group_key", "status"],
    )
    op.create_index(
        "ix_tenant_notification_recipients_tenant_channel_status",
        "tenant_notification_recipients",
        ["tenant_id", "channel", "status"],
    )

    op.create_table(
        "tenant_notification_rules",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("capability_key", sa.String(length=80), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("action_type", sa.String(length=80), nullable=False),
        sa.Column("template_key", sa.String(length=120), nullable=True),
        sa.Column("recipient_strategy", sa.String(length=40), nullable=False),
        sa.Column("recipient_group_key", sa.String(length=80), nullable=True),
        sa.Column("conditions_json", sa.JSON(), nullable=False),
        sa.Column("variable_mapping_json", sa.JSON(), nullable=False),
        sa.Column("schedule_mode", sa.String(length=40), nullable=False, server_default="immediate"),
        sa.Column("schedule_offset_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_tenant_notification_rules_tenant_name"),
    )
    op.create_index(
        "ix_tenant_notification_rules_tenant_event_enabled",
        "tenant_notification_rules",
        ["tenant_id", "event_type", "enabled"],
    )
    op.create_index(
        "ix_tenant_notification_rules_tenant_capability_enabled",
        "tenant_notification_rules",
        ["tenant_id", "capability_key", "enabled"],
    )
    op.create_index(
        "ix_tenant_notification_rules_tenant_priority",
        "tenant_notification_rules",
        ["tenant_id", "priority"],
    )

    op.create_table(
        "domain_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=True),
        sa.Column("resource_id", sa.String(length=80), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_domain_events_tenant_idempotency_key"),
    )
    op.create_index(
        "ix_domain_events_tenant_event_status", "domain_events", ["tenant_id", "event_type", "status"]
    )
    op.create_index("ix_domain_events_status_available_at", "domain_events", ["status", "available_at"])
    op.create_index(
        "ix_domain_events_tenant_resource", "domain_events", ["tenant_id", "resource_type", "resource_id"]
    )
    op.create_index("ix_domain_events_tenant_correlation", "domain_events", ["tenant_id", "correlation_id"])

    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "domain_event_id", sa.String(length=36), sa.ForeignKey("domain_events.id"), nullable=False
        ),
        sa.Column(
            "notification_rule_id",
            sa.String(length=36),
            sa.ForeignKey("tenant_notification_rules.id"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("recipient", sa.String(length=255), nullable=False),
        sa.Column("template_key", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_notification_deliveries_tenant_idempotency_key"
        ),
    )
    op.create_index(
        "ix_notification_deliveries_tenant_status_scheduled",
        "notification_deliveries",
        ["tenant_id", "status", "scheduled_for"],
    )
    op.create_index(
        "ix_notification_deliveries_status_scheduled",
        "notification_deliveries",
        ["status", "scheduled_for"],
    )
    op.create_index(
        "ix_notification_deliveries_tenant_provider_message",
        "notification_deliveries",
        ["tenant_id", "provider_message_id"],
    )
    op.create_index(
        "ix_notification_deliveries_tenant_domain_event",
        "notification_deliveries",
        ["tenant_id", "domain_event_id"],
    )
    op.create_index(
        "ix_notification_deliveries_tenant_rule",
        "notification_deliveries",
        ["tenant_id", "notification_rule_id"],
    )


def downgrade() -> None:
    op.drop_table("notification_deliveries")
    op.drop_table("domain_events")
    op.drop_table("tenant_notification_rules")
    op.drop_table("tenant_notification_recipients")
    op.drop_table("tenant_capabilities")
