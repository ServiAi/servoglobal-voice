"""add tenant feature grants

Revision ID: 202608040001
Revises: 202607270001
"""

from alembic import op
import sqlalchemy as sa


revision = "202608040001"
down_revision = "202607270001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_feature_grants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("feature_key", sa.String(length=80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("limits_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("enabled_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["enabled_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "feature_key",
            name="uq_tenant_feature_grants_tenant_feature_key",
        ),
    )
    op.create_index(
        "ix_tenant_feature_grants_tenant_id",
        "tenant_feature_grants",
        ["tenant_id"],
    )
    op.create_index(
        "ix_tenant_feature_grants_feature_key",
        "tenant_feature_grants",
        ["feature_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_feature_grants_feature_key", table_name="tenant_feature_grants")
    op.drop_index("ix_tenant_feature_grants_tenant_id", table_name="tenant_feature_grants")
    op.drop_table("tenant_feature_grants")
