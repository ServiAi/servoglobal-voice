"""add notification worker state

Revision ID: 202607270001
Revises: 202607240001
"""

from alembic import op
import sqlalchemy as sa


revision = "202607270001"
down_revision = "202607240001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_deliveries",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "notification_deliveries",
        sa.Column("claim_token", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "notification_deliveries",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "notification_deliveries",
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        "ix_notification_deliveries_worker_due",
        "notification_deliveries",
        ["status", "next_attempt_at", "scheduled_for"],
    )
    op.create_index(
        "ix_notification_deliveries_processing_lease",
        "notification_deliveries",
        ["status", "claim_expires_at"],
    )

    notification_deliveries = sa.table(
        "notification_deliveries",
        sa.column("status", sa.String),
        sa.column("scheduled_for", sa.DateTime(timezone=True)),
        sa.column("next_attempt_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        notification_deliveries.update()
        .where(notification_deliveries.c.status.in_(("pending", "failed")))
        .values(next_attempt_at=notification_deliveries.c.scheduled_for)
    )

    op.add_column(
        "crm_whatsapp_messages",
        sa.Column("notification_delivery_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_crm_whatsapp_messages_notification_delivery_id",
        "crm_whatsapp_messages",
        "notification_deliveries",
        ["notification_delivery_id"],
        ["id"],
    )
    op.create_index(
        "ix_crm_whatsapp_messages_tenant_notification_delivery",
        "crm_whatsapp_messages",
        ["tenant_id", "notification_delivery_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_crm_whatsapp_messages_tenant_notification_delivery",
        table_name="crm_whatsapp_messages",
    )
    op.drop_constraint(
        "fk_crm_whatsapp_messages_notification_delivery_id",
        "crm_whatsapp_messages",
        type_="foreignkey",
    )
    op.drop_column("crm_whatsapp_messages", "notification_delivery_id")

    op.drop_index("ix_notification_deliveries_processing_lease", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_worker_due", table_name="notification_deliveries")
    op.drop_column("notification_deliveries", "claim_expires_at")
    op.drop_column("notification_deliveries", "claimed_at")
    op.drop_column("notification_deliveries", "claim_token")
    op.drop_column("notification_deliveries", "next_attempt_at")
