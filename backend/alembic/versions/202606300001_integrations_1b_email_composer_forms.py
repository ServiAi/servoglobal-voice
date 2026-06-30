"""add email composer assets and form links

Revision ID: 202606300001
Revises: 202606270001
Create Date: 2026-06-30 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202606300001"
down_revision = "202606270001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_email_send_assets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("email_send_id", sa.String(length=36), sa.ForeignKey("tenant_email_sends.id"), nullable=False),
        sa.Column("asset_id", sa.String(length=36), sa.ForeignKey("tenant_email_assets.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email_send_id", "asset_id", name="uq_tenant_email_send_assets_send_asset"),
    )
    op.create_index("ix_tenant_email_send_assets_tenant_send", "tenant_email_send_assets", ["tenant_id", "email_send_id"])

    op.create_table(
        "tenant_forms",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tenant_forms_tenant_status", "tenant_forms", ["tenant_id", "status"])

    op.create_table(
        "tenant_form_fields",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("form_id", sa.String(length=36), sa.ForeignKey("tenant_forms.id"), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("field_type", sa.String(length=32), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("options_json", sa.JSON(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("form_id", "key", name="uq_tenant_form_fields_form_key"),
    )
    op.create_index("ix_tenant_form_fields_tenant_form", "tenant_form_fields", ["tenant_id", "form_id"])

    op.create_table(
        "tenant_form_tokens",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("form_id", sa.String(length=36), sa.ForeignKey("tenant_forms.id"), nullable=False),
        sa.Column("lead_id", sa.String(length=36), sa.ForeignKey("crm_leads.id"), nullable=False),
        sa.Column("contact_id", sa.String(length=36), sa.ForeignKey("crm_contacts.id"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tenant_form_tokens_token_hash", "tenant_form_tokens", ["token_hash"])
    op.create_index("ix_tenant_form_tokens_tenant_lead", "tenant_form_tokens", ["tenant_id", "lead_id"])

    op.create_table(
        "tenant_form_submissions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("form_id", sa.String(length=36), sa.ForeignKey("tenant_forms.id"), nullable=False),
        sa.Column("lead_id", sa.String(length=36), sa.ForeignKey("crm_leads.id"), nullable=False),
        sa.Column("contact_id", sa.String(length=36), sa.ForeignKey("crm_contacts.id"), nullable=False),
        sa.Column("token_id", sa.String(length=36), sa.ForeignKey("tenant_form_tokens.id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tenant_form_submissions_tenant_lead", "tenant_form_submissions", ["tenant_id", "lead_id"])
    op.create_index("ix_tenant_form_submissions_token", "tenant_form_submissions", ["token_id"])

    op.create_table(
        "tenant_form_submission_answers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("submission_id", sa.String(length=36), sa.ForeignKey("tenant_form_submissions.id"), nullable=False),
        sa.Column("field_id", sa.String(length=36), sa.ForeignKey("tenant_form_fields.id"), nullable=True),
        sa.Column("field_key", sa.String(length=80), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_tenant_form_submission_answers_tenant_submission",
        "tenant_form_submission_answers",
        ["tenant_id", "submission_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_form_submission_answers_tenant_submission", table_name="tenant_form_submission_answers")
    op.drop_table("tenant_form_submission_answers")
    op.drop_index("ix_tenant_form_submissions_token", table_name="tenant_form_submissions")
    op.drop_index("ix_tenant_form_submissions_tenant_lead", table_name="tenant_form_submissions")
    op.drop_table("tenant_form_submissions")
    op.drop_index("ix_tenant_form_tokens_tenant_lead", table_name="tenant_form_tokens")
    op.drop_index("ix_tenant_form_tokens_token_hash", table_name="tenant_form_tokens")
    op.drop_table("tenant_form_tokens")
    op.drop_index("ix_tenant_form_fields_tenant_form", table_name="tenant_form_fields")
    op.drop_table("tenant_form_fields")
    op.drop_index("ix_tenant_forms_tenant_status", table_name="tenant_forms")
    op.drop_table("tenant_forms")
    op.drop_index("ix_tenant_email_send_assets_tenant_send", table_name="tenant_email_send_assets")
    op.drop_table("tenant_email_send_assets")
