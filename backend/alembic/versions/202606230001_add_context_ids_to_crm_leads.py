"""add context ids to crm leads

Revision ID: 202606230001
Revises: 202606220001
Create Date: 2026-06-23 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "202606230001"
down_revision = "202606220001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("crm_leads", sa.Column("form_submission_id", sa.String(length=36), nullable=True))
    op.add_column("crm_leads", sa.Column("context_id", sa.String(length=36), nullable=True))

    op.create_index(
        "ix_crm_leads_tenant_form_submission",
        "crm_leads",
        ["tenant_id", "form_submission_id"],
    )
    op.create_index(
        "ix_crm_leads_tenant_context_id",
        "crm_leads",
        ["tenant_id", "context_id"],
    )
    op.create_index(
        "uq_crm_leads_tenant_form_submission",
        "crm_leads",
        ["tenant_id", "form_submission_id"],
        unique=True,
        postgresql_where=sa.text("form_submission_id IS NOT NULL"),
        sqlite_where=sa.text("form_submission_id IS NOT NULL"),
    )
    op.create_index(
        "uq_crm_leads_tenant_context_id",
        "crm_leads",
        ["tenant_id", "context_id"],
        unique=True,
        postgresql_where=sa.text("context_id IS NOT NULL"),
        sqlite_where=sa.text("context_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_crm_leads_tenant_context_id", table_name="crm_leads")
    op.drop_index("uq_crm_leads_tenant_form_submission", table_name="crm_leads")
    op.drop_index("ix_crm_leads_tenant_context_id", table_name="crm_leads")
    op.drop_index("ix_crm_leads_tenant_form_submission", table_name="crm_leads")
    op.drop_column("crm_leads", "context_id")
    op.drop_column("crm_leads", "form_submission_id")
