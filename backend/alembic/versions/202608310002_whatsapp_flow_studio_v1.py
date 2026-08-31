"""Add WhatsApp Flow Studio persistence.

Revision ID: 202608310002
Revises: 202608310001
"""

from alembic import op
import sqlalchemy as sa


revision = "202608310002"
down_revision = "202608310001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_whatsapp_flows",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("flow_key", sa.String(length=80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("parent_flow_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("categories_json", sa.JSON(), nullable=False),
        sa.Column("source_mode", sa.String(length=24), nullable=False),
        sa.Column("context_schema_id", sa.String(length=36), nullable=True),
        sa.Column("context_schema_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("meta_status", sa.String(length=32), nullable=True),
        sa.Column("provider_flow_id", sa.String(length=120), nullable=True),
        sa.Column("builder_schema_version", sa.Integer(), nullable=False),
        sa.Column("builder_json", sa.JSON(), nullable=False),
        sa.Column("compiled_flow_json", sa.JSON(), nullable=True),
        sa.Column("compiled_hash", sa.String(length=64), nullable=True),
        sa.Column("synced_hash", sa.String(length=64), nullable=True),
        sa.Column("validation_errors_json", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["context_schema_id"], ["tenant_voice_context_schemas.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_flow_id"], ["tenant_whatsapp_flows.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "flow_key", "version", name="uq_tenant_whatsapp_flows_tenant_key_version"),
    )
    op.create_index("ix_tenant_whatsapp_flows_tenant_status", "tenant_whatsapp_flows", ["tenant_id", "status"])
    op.create_index("ix_tenant_whatsapp_flows_tenant_provider", "tenant_whatsapp_flows", ["tenant_id", "provider_flow_id"])
    op.create_index("ix_tenant_whatsapp_flows_tenant_key", "tenant_whatsapp_flows", ["tenant_id", "flow_key"])


def downgrade() -> None:
    op.drop_index("ix_tenant_whatsapp_flows_tenant_key", table_name="tenant_whatsapp_flows")
    op.drop_index("ix_tenant_whatsapp_flows_tenant_provider", table_name="tenant_whatsapp_flows")
    op.drop_index("ix_tenant_whatsapp_flows_tenant_status", table_name="tenant_whatsapp_flows")
    op.drop_table("tenant_whatsapp_flows")
