"""Scheduling consistency: idempotent booking operations + explicit resource column.

Revision ID: 202609240001
Revises: 202609230001
"""

from alembic import op
import sqlalchemy as sa


revision = "202609240001"
down_revision = "202609230001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("crm_bookings", sa.Column("scheduling_resource_id", sa.String(36), nullable=True))
    op.create_foreign_key(
        "fk_crm_bookings_scheduling_resource",
        "crm_bookings",
        "tenant_scheduling_resources",
        ["scheduling_resource_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_crm_bookings_resource_interval",
        "crm_bookings",
        ["tenant_id", "scheduling_resource_id", "start_at", "end_at"],
    )
    # Safe backfill: only ids that exist for the same tenant; anything else stays NULL.
    op.execute(
        """
        UPDATE crm_bookings b
        SET scheduling_resource_id = r.id
        FROM tenant_scheduling_resources r
        WHERE r.id = (b.metadata_json::jsonb ->> 'scheduling_resource_id')
          AND r.tenant_id = b.tenant_id
        """
    )

    op.create_table(
        "tenant_booking_operations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("operation_type", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("booking_id", sa.String(36), sa.ForeignKey("crm_bookings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("provider", sa.String(40), nullable=True),
        sa.Column("provider_operation_id", sa.String(255), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "operation_type", "idempotency_key", name="uq_tenant_booking_operations_key"),
    )
    op.create_index("ix_tenant_booking_operations_booking", "tenant_booking_operations", ["tenant_id", "booking_id"])


def downgrade() -> None:
    op.drop_index("ix_tenant_booking_operations_booking", table_name="tenant_booking_operations")
    op.drop_table("tenant_booking_operations")
    op.drop_index("ix_crm_bookings_resource_interval", table_name="crm_bookings")
    op.drop_constraint("fk_crm_bookings_scheduling_resource", "crm_bookings", type_="foreignkey")
    op.drop_column("crm_bookings", "scheduling_resource_id")
