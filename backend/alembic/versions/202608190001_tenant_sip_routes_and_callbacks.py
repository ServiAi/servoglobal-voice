"""add tenant SIP routes and public callback linkage

Revision ID: 202608190001
Revises: 202608180002
"""

import sqlalchemy as sa
from alembic import op

revision = "202608190001"
down_revision = "202608180002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_sip_routes",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("provider_config_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("pbx_host", sa.String(255), nullable=False),
        sa.Column("pbx_port", sa.Integer(), nullable=False),
        sa.Column("sip_username", sa.String(120), nullable=False),
        sa.Column("sip_password_encrypted", sa.Text(), nullable=True),
        sa.Column("caller_id", sa.String(32), nullable=False),
        sa.Column("default_country", sa.String(2), nullable=False),
        sa.Column("allowed_countries_json", sa.JSON(), nullable=False),
        sa.Column("max_concurrent_calls", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('active','inactive')", name="ck_tenant_sip_routes_status"),
        sa.CheckConstraint("pbx_port BETWEEN 1 AND 65535", name="ck_tenant_sip_routes_port"),
        sa.CheckConstraint("max_concurrent_calls BETWEEN 1 AND 100", name="ck_tenant_sip_routes_concurrency"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["provider_config_id"], ["tenant_voice_provider_configs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_sip_routes_tenant"),
        sa.UniqueConstraint(
            "provider_config_id", name="uq_tenant_sip_routes_provider_config"
        ),
    )
    op.create_index(
        "ix_tenant_sip_routes_tenant_status", "tenant_sip_routes", ["tenant_id", "status"]
    )
    op.add_column(
        "crm_voice_calls", sa.Column("source_submission_id", sa.String(36), nullable=True)
    )
    op.add_column("crm_voice_calls", sa.Column("sip_route_id", sa.String(36), nullable=True))
    op.add_column(
        "crm_voice_calls",
        sa.Column("provider_attempt_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_crm_voice_calls_source_submission",
        "crm_voice_calls",
        "tenant_voice_experience_submissions",
        ["source_submission_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_crm_voice_calls_sip_route",
        "crm_voice_calls",
        "tenant_sip_routes",
        ["sip_route_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_crm_voice_calls_source_submission", "crm_voice_calls", ["source_submission_id"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_crm_voice_calls_source_submission", "crm_voice_calls", type_="unique"
    )
    op.drop_constraint("fk_crm_voice_calls_sip_route", "crm_voice_calls", type_="foreignkey")
    op.drop_constraint(
        "fk_crm_voice_calls_source_submission", "crm_voice_calls", type_="foreignkey"
    )
    op.drop_column("crm_voice_calls", "provider_attempt_started_at")
    op.drop_column("crm_voice_calls", "sip_route_id")
    op.drop_column("crm_voice_calls", "source_submission_id")
    op.drop_index("ix_tenant_sip_routes_tenant_status", table_name="tenant_sip_routes")
    op.drop_table("tenant_sip_routes")
