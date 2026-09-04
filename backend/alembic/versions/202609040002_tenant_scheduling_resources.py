"""tenant scheduling resources and round robin

Revision ID: 202609040002
Revises: 202609040001
Create Date: 2026-09-04 01:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202609040002"
down_revision = "202609040001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_scheduling_resources",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=False, server_default="user"),
        sa.Column("team", sa.String(length=80), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=80), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("timezone", sa.String(length=80), nullable=False, server_default="America/Bogota"),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("working_hours_json", sa.JSON(), nullable=True),
        sa.Column("total_assigned_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_tenant_scheduling_resources_tenant_team",
        "tenant_scheduling_resources",
        ["tenant_id", "team"],
    )
    op.create_index(
        "ix_tenant_scheduling_resources_tenant_active",
        "tenant_scheduling_resources",
        ["tenant_id", "is_active"],
    )

    op.create_table(
        "tenant_scheduling_resource_calendars",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("resource_id", sa.String(length=36), sa.ForeignKey("tenant_scheduling_resources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("calendar_id", sa.String(length=36), sa.ForeignKey("tenant_google_calendars.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_blocking", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_destination", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("resource_id", "calendar_id", name="uq_tenant_resource_calendars_res_cal"),
    )
    op.create_index(
        "ix_tenant_scheduling_resource_calendars_tenant_resource",
        "tenant_scheduling_resource_calendars",
        ["tenant_id", "resource_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_scheduling_resource_calendars_tenant_resource", table_name="tenant_scheduling_resource_calendars")
    op.drop_table("tenant_scheduling_resource_calendars")
    op.drop_index("ix_tenant_scheduling_resources_tenant_active", table_name="tenant_scheduling_resources")
    op.drop_index("ix_tenant_scheduling_resources_tenant_team", table_name="tenant_scheduling_resources")
    op.drop_table("tenant_scheduling_resources")
