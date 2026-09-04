"""tenant scheduling engine: configs, exceptions, teams, team members and agent configs

Revision ID: 202609040003
Revises: 202609040002
Create Date: 2026-09-04 18:15:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202609040003"
down_revision = "202609040002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Tenant Scheduling Configs
    op.create_table(
        "tenant_scheduling_configs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("timezone", sa.String(length=80), nullable=False, server_default="America/Bogota"),
        sa.Column("default_duration_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("slot_interval_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("buffer_before_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("buffer_after_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("minimum_notice_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("maximum_booking_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("routing_strategy", sa.String(length=40), nullable=False, server_default="single"),
        sa.Column("default_resource_id", sa.String(length=36), nullable=True),
        sa.Column("default_team_id", sa.String(length=36), nullable=True),
        sa.Column("working_hours_json", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_scheduling_configs_tenant"),
    )
    op.create_index("ix_tenant_scheduling_configs_tenant", "tenant_scheduling_configs", ["tenant_id"])

    # 2. Scheduling Teams
    op.create_table(
        "tenant_scheduling_teams",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("routing_strategy", sa.String(length=40), nullable=False, server_default="round_robin"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tenant_scheduling_teams_tenant", "tenant_scheduling_teams", ["tenant_id"])

    # 3. Scheduling Team Members
    op.create_table(
        "tenant_scheduling_team_members",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("team_id", sa.String(length=36), sa.ForeignKey("tenant_scheduling_teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource_id", sa.String(length=36), sa.ForeignKey("tenant_scheduling_resources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("team_id", "resource_id", name="uq_tenant_team_members_team_resource"),
    )
    op.create_index("ix_tenant_scheduling_team_members_tenant_team", "tenant_scheduling_team_members", ["tenant_id", "team_id"])

    # 4. Scheduling Availability Exceptions
    op.create_table(
        "tenant_scheduling_exceptions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("resource_id", sa.String(length=36), sa.ForeignKey("tenant_scheduling_resources.id", ondelete="CASCADE"), nullable=True),
        sa.Column("exception_date", sa.Date(), nullable=False),
        sa.Column("exception_type", sa.String(length=40), nullable=False, server_default="unavailable"),
        sa.Column("start_time", sa.String(length=8), nullable=True),
        sa.Column("end_time", sa.String(length=8), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tenant_scheduling_exceptions_tenant_date", "tenant_scheduling_exceptions", ["tenant_id", "exception_date"])
    op.create_index("ix_tenant_scheduling_exceptions_resource_date", "tenant_scheduling_exceptions", ["resource_id", "exception_date"])

    # 5. Agent Scheduling Configs
    op.create_table(
        "tenant_agent_scheduling_configs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("agent_id", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False, server_default="google_calendar"),
        sa.Column("scheduling_config_id", sa.String(length=36), sa.ForeignKey("tenant_scheduling_configs.id"), nullable=True),
        sa.Column("resource_id", sa.String(length=36), sa.ForeignKey("tenant_scheduling_resources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("team_id", sa.String(length=36), sa.ForeignKey("tenant_scheduling_teams.id", ondelete="SET NULL"), nullable=True),
        sa.Column("routing_strategy", sa.String(length=40), nullable=False, server_default="single"),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("allow_check_availability", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("allow_create_booking", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("allow_reschedule", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("allow_cancel", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "agent_id", name="uq_tenant_agent_scheduling_tenant_agent"),
    )
    op.create_index("ix_tenant_agent_scheduling_tenant_agent", "tenant_agent_scheduling_configs", ["tenant_id", "agent_id"])


def downgrade() -> None:
    op.drop_table("tenant_agent_scheduling_configs")
    op.drop_table("tenant_scheduling_exceptions")
    op.drop_table("tenant_scheduling_team_members")
    op.drop_table("tenant_scheduling_teams")
    op.drop_table("tenant_scheduling_configs")
