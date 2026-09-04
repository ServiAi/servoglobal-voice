"""tenant google calendars

Revision ID: 202609040001
Revises: 202609030001
Create Date: 2026-09-04 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202609040001"
down_revision = "202609030001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_google_calendars",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("connection_id", sa.String(length=36), sa.ForeignKey("tenant_google_calendar_connections.id"), nullable=False),
        sa.Column("google_calendar_id", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("time_zone", sa.String(length=80), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_blocking", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_booking_destination", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("access_role", sa.String(length=80), nullable=True),
        sa.Column("sync_token", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("connection_id", "google_calendar_id", name="uq_tenant_google_calendars_conn_cal"),
    )
    op.create_index(
        "ix_tenant_google_calendars_tenant_conn",
        "tenant_google_calendars",
        ["tenant_id", "connection_id"],
    )
    op.create_index(
        "ix_tenant_google_calendars_tenant_blocking",
        "tenant_google_calendars",
        ["tenant_id", "is_blocking"],
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_google_calendars_tenant_blocking", table_name="tenant_google_calendars")
    op.drop_index("ix_tenant_google_calendars_tenant_conn", table_name="tenant_google_calendars")
    op.drop_table("tenant_google_calendars")
