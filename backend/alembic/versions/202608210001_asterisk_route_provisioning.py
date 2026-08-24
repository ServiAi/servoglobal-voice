"""add Asterisk provisioning state to tenant SIP routes

Revision ID: 202608210001
Revises: 202608190001
"""

import sqlalchemy as sa
from alembic import op

revision = "202608210001"
down_revision = "202608190001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_tenant_sip_routes_sip_username", "tenant_sip_routes", ["sip_username"]
    )
    op.add_column(
        "tenant_sip_routes",
        sa.Column("provision_status", sa.String(16), nullable=False, server_default="pending"),
    )
    op.add_column(
        "tenant_sip_routes",
        sa.Column("desired_revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "tenant_sip_routes",
        sa.Column("applied_revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "tenant_sip_routes", sa.Column("provision_error_code", sa.String(80), nullable=True)
    )
    op.add_column(
        "tenant_sip_routes",
        sa.Column("provisioned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tenant_sip_routes",
        sa.Column("last_provision_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_tenant_sip_routes_provision_status",
        "tenant_sip_routes",
        "provision_status IN ('pending','active','failed','disabled')",
    )
    op.alter_column("tenant_sip_routes", "provision_status", server_default=None)
    op.alter_column("tenant_sip_routes", "desired_revision", server_default=None)
    op.alter_column("tenant_sip_routes", "applied_revision", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "ck_tenant_sip_routes_provision_status", "tenant_sip_routes", type_="check"
    )
    op.drop_column("tenant_sip_routes", "last_provision_attempt_at")
    op.drop_column("tenant_sip_routes", "provisioned_at")
    op.drop_column("tenant_sip_routes", "provision_error_code")
    op.drop_column("tenant_sip_routes", "applied_revision")
    op.drop_column("tenant_sip_routes", "desired_revision")
    op.drop_column("tenant_sip_routes", "provision_status")
    op.drop_constraint(
        "uq_tenant_sip_routes_sip_username", "tenant_sip_routes", type_="unique"
    )
