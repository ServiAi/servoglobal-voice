"""calcom scheduling provider entities: schedules, event_types, provider_objects, agent_config event_type_id

Revision ID: 202609050001
Revises: 202609040003
Create Date: 2026-09-05 16:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202609050001"
down_revision = "202609040003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Tenant Scheduling Schedules (Projections)
    op.create_table(
        "tenant_scheduling_schedules",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False, server_default="calcom"),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("timezone", sa.String(length=80), nullable=False, server_default="America/Bogota"),
        sa.Column("working_hours_json", sa.JSON(), nullable=True),
        sa.Column("overrides_json", sa.JSON(), nullable=True),
        sa.Column("provider_schedule_id", sa.String(length=80), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", sa.String(length=32), nullable=False, server_default="synced"),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_tenant_scheduling_schedules_tenant_id",
        "tenant_scheduling_schedules",
        ["tenant_id"],
    )
    op.create_index(
        "ix_tenant_scheduling_schedules_tenant_provider",
        "tenant_scheduling_schedules",
        ["tenant_id", "provider"],
    )
    op.create_index(
        "ix_tenant_scheduling_schedules_tenant_provider_ext",
        "tenant_scheduling_schedules",
        ["tenant_id", "provider", "provider_schedule_id"],
    )
    op.create_index(
        "ix_tenant_scheduling_schedules_tenant_status",
        "tenant_scheduling_schedules",
        ["tenant_id", "sync_status"],
    )

    # 2. Tenant Scheduling Event Types
    op.create_table(
        "tenant_scheduling_event_types",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False, server_default="calcom"),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("slot_interval_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("buffer_before_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("buffer_after_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("minimum_notice_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("timezone", sa.String(length=80), nullable=False, server_default="America/Bogota"),
        sa.Column(
            "local_schedule_id",
            sa.String(length=36),
            sa.ForeignKey("tenant_scheduling_schedules.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "local_team_id",
            sa.String(length=36),
            sa.ForeignKey("tenant_scheduling_teams.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider_event_type_id", sa.String(length=80), nullable=True),
        sa.Column("provider_event_type_slug", sa.String(length=160), nullable=True),
        sa.Column("provider_config_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", sa.String(length=32), nullable=False, server_default="synced"),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_tenant_scheduling_event_types_tenant_id",
        "tenant_scheduling_event_types",
        ["tenant_id"],
    )
    op.create_index(
        "ix_tenant_scheduling_event_types_tenant_provider",
        "tenant_scheduling_event_types",
        ["tenant_id", "provider"],
    )
    op.create_index(
        "ix_tenant_scheduling_event_types_tenant_provider_ext",
        "tenant_scheduling_event_types",
        ["tenant_id", "provider", "provider_event_type_id"],
    )
    op.create_index(
        "ix_tenant_scheduling_event_types_tenant_status",
        "tenant_scheduling_event_types",
        ["tenant_id", "sync_status"],
    )

    # 3. Tenant Scheduling Provider Objects
    op.create_table(
        "tenant_scheduling_provider_objects",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("object_type", sa.String(length=40), nullable=False),
        sa.Column("local_object_id", sa.String(length=36), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("external_slug", sa.String(length=255), nullable=True),
        sa.Column("provider_metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("sync_status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "provider", "object_type", "external_id",
            name="uq_tenant_provider_object",
        ),
    )
    op.create_index(
        "ix_tenant_provider_objects_tenant_provider",
        "tenant_scheduling_provider_objects",
        ["tenant_id", "provider"],
    )
    op.create_index(
        "ix_tenant_provider_objects_tenant_status",
        "tenant_scheduling_provider_objects",
        ["tenant_id", "sync_status"],
    )

    # 4. Add event_type_id to tenant_agent_scheduling_configs
    with op.batch_alter_table("tenant_agent_scheduling_configs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "event_type_id",
                sa.String(length=36),
                sa.ForeignKey("tenant_scheduling_event_types.id", ondelete="SET NULL"),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("tenant_agent_scheduling_configs") as batch_op:
        batch_op.drop_column("event_type_id")

    op.drop_table("tenant_scheduling_provider_objects")
    op.drop_table("tenant_scheduling_event_types")
    op.drop_table("tenant_scheduling_schedules")
