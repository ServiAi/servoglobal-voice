"""sprint 2 analytics foundation

Revision ID: 202605020001
Revises: 202605010001
Create Date: 2026-05-02 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "202605020001"
down_revision = "202605010001"
branch_labels = None
depends_on = None

timestamp_column = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("external_provider", sa.String(length=80), nullable=True),
        sa.Column("external_agent_id", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("channel_type", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", timestamp_column, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", timestamp_column, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "external_provider",
            "external_agent_id",
            name="uq_agents_tenant_provider_external_agent",
        ),
    )
    op.create_index("ix_agents_external_agent_id", "agents", ["external_agent_id"])
    op.create_index("ix_agents_tenant_id", "agents", ["tenant_id"])
    op.create_index("ix_agents_tenant_status", "agents", ["tenant_id", "status"])

    op.create_table(
        "calls",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("external_call_id", sa.String(length=255), nullable=True),
        sa.Column("external_provider", sa.String(length=80), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("provider_agent_id", sa.String(length=255), nullable=True),
        sa.Column("provider_status", sa.String(length=120), nullable=True),
        sa.Column("normalized_status", sa.String(length=32), nullable=False),
        sa.Column("started_at", timestamp_column, nullable=False),
        sa.Column("joined_at", timestamp_column, nullable=True),
        sa.Column("ended_at", timestamp_column, nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("billed_minutes", sa.Numeric(10, 2), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("short_summary", sa.String(length=500), nullable=True),
        sa.Column("recording_url", sa.Text(), nullable=True),
        sa.Column("direction", sa.String(length=32), nullable=True),
        sa.Column("customer_phone", sa.String(length=80), nullable=True),
        sa.Column("last_synced_at", timestamp_column, nullable=True),
        sa.Column("created_at", timestamp_column, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", timestamp_column, server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "normalized_status in ("
            "'in_progress', 'answered', 'unanswered', 'rejected', "
            "'failed', 'cancelled', 'transferred', 'voicemail'"
            ")",
            name="ck_calls_normalized_status",
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "external_provider",
            "external_call_id",
            name="uq_calls_tenant_provider_external_call",
        ),
    )
    op.create_index("ix_calls_external_call_id", "calls", ["external_call_id"])
    op.create_index("ix_calls_started_at", "calls", ["started_at"])
    op.create_index("ix_calls_tenant_agent_id", "calls", ["tenant_id", "agent_id"])
    op.create_index(
        "ix_calls_tenant_normalized_status", "calls", ["tenant_id", "normalized_status"]
    )
    op.create_index("ix_calls_tenant_id", "calls", ["tenant_id"])
    op.create_index("ix_calls_tenant_started_at", "calls", ["tenant_id", "started_at"])

    op.create_table(
        "call_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("call_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("provider_event_id", sa.String(length=255), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("received_at", timestamp_column, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_call_events_call_id", "call_events", ["call_id"])
    op.create_index("ix_call_events_received_at", "call_events", ["received_at"])
    op.create_index("ix_call_events_tenant_id", "call_events", ["tenant_id"])
    op.create_index(
        "ix_call_events_tenant_received_at", "call_events", ["tenant_id", "received_at"]
    )

    op.create_table(
        "metric_snapshots_daily",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("calls_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("calls_answered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("calls_unanswered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_total_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("billed_minutes", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("created_at", timestamp_column, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", timestamp_column, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "agent_id",
            "date",
            name="uq_metric_snapshots_daily_tenant_agent_date",
        ),
    )
    op.create_index(
        "ix_metric_snapshots_daily_tenant_agent_date",
        "metric_snapshots_daily",
        ["tenant_id", "agent_id", "date"],
    )
    op.create_index(
        "ix_metric_snapshots_daily_tenant_date",
        "metric_snapshots_daily",
        ["tenant_id", "date"],
    )


def downgrade() -> None:
    op.drop_index("ix_metric_snapshots_daily_tenant_date", table_name="metric_snapshots_daily")
    op.drop_index(
        "ix_metric_snapshots_daily_tenant_agent_date",
        table_name="metric_snapshots_daily",
    )
    op.drop_table("metric_snapshots_daily")

    op.drop_index("ix_call_events_tenant_received_at", table_name="call_events")
    op.drop_index("ix_call_events_tenant_id", table_name="call_events")
    op.drop_index("ix_call_events_received_at", table_name="call_events")
    op.drop_index("ix_call_events_call_id", table_name="call_events")
    op.drop_table("call_events")

    op.drop_index("ix_calls_tenant_started_at", table_name="calls")
    op.drop_index("ix_calls_tenant_id", table_name="calls")
    op.drop_index("ix_calls_tenant_normalized_status", table_name="calls")
    op.drop_index("ix_calls_tenant_agent_id", table_name="calls")
    op.drop_index("ix_calls_started_at", table_name="calls")
    op.drop_index("ix_calls_external_call_id", table_name="calls")
    op.drop_table("calls")

    op.drop_index("ix_agents_tenant_status", table_name="agents")
    op.drop_index("ix_agents_tenant_id", table_name="agents")
    op.drop_index("ix_agents_external_agent_id", table_name="agents")
    op.drop_table("agents")
