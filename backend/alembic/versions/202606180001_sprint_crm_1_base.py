"""sprint crm 1 base tables

Revision ID: 202606180001
Revises: 202605300001
Create Date: 2026-06-18 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "202606180001"
down_revision = "202605300001"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. crm_contacts
    op.create_table(
        "crm_contacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False, server_default="Lead sin nombre"),
        sa.Column("phone", sa.String(80), nullable=True),
        sa.Column("phone_normalized", sa.String(80), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("source", sa.String(120), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "phone_normalized", name="uq_crm_contacts_tenant_phone"),
    )
    op.create_index("ix_crm_contacts_tenant_id", "crm_contacts", ["tenant_id"])
    op.create_index("ix_crm_contacts_phone_normalized", "crm_contacts", ["phone_normalized"])
    op.create_index("ix_crm_contacts_email", "crm_contacts", ["email"])
    # Partial unique index for tenant_id + email where email is not null
    op.create_index(
        "ix_crm_contacts_tenant_email_uniq",
        "crm_contacts",
        ["tenant_id", "email"],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )

    # 2. crm_pipeline_stages
    op.create_table(
        "crm_pipeline_stages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("is_terminal", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "key", name="uq_crm_pipeline_stages_tenant_key"),
    )
    op.create_index("ix_crm_pipeline_stages_tenant_key", "crm_pipeline_stages", ["tenant_id", "key"])

    # 3. crm_leads
    op.create_table(
        "crm_leads",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_id", sa.String(36), sa.ForeignKey("crm_contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("current_stage_id", sa.String(36), sa.ForeignKey("crm_pipeline_stages.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("lead_score", sa.Integer(), nullable=True),
        sa.Column("interest", sa.String(255), nullable=True),
        sa.Column("industry", sa.String(255), nullable=True),
        sa.Column("use_case", sa.String(255), nullable=True),
        sa.Column("volume", sa.String(255), nullable=True),
        sa.Column("pain_point", sa.Text(), nullable=True),
        sa.Column("budget_range", sa.String(255), nullable=True),
        sa.Column("intent_level", sa.String(80), nullable=True),
        sa.Column("next_action", sa.String(255), nullable=True),
        sa.Column("owner_agent_id", sa.String(36), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_from_call_id", sa.String(36), sa.ForeignKey("calls.id", ondelete="SET NULL"), nullable=True),
        sa.Column("last_call_id", sa.String(36), sa.ForeignKey("calls.id", ondelete="SET NULL"), nullable=True),
        sa.Column("short_summary", sa.String(500), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source", sa.String(120), nullable=True),
        sa.Column("campaign", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_crm_leads_tenant_contact_status", "crm_leads", ["tenant_id", "contact_id", "status"])
    op.create_index("ix_crm_leads_tenant_last_call", "crm_leads", ["tenant_id", "last_call_id"])

    # 4. crm_activities
    op.create_table(
        "crm_activities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lead_id", sa.String(36), sa.ForeignKey("crm_leads.id", ondelete="CASCADE"), nullable=True),
        sa.Column("contact_id", sa.String(36), sa.ForeignKey("crm_contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("call_id", sa.String(36), sa.ForeignKey("calls.id", ondelete="SET NULL"), nullable=True),
        sa.Column("activity_type", sa.String(80), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("outcome", sa.String(255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "call_id", "activity_type", name="uq_crm_activities_tenant_call_type"),
    )
    op.create_index("ix_crm_activities_tenant_call_type", "crm_activities", ["tenant_id", "call_id", "activity_type"])
    op.create_index("ix_crm_activities_tenant_contact", "crm_activities", ["tenant_id", "contact_id"])
    op.create_index("ix_crm_activities_occurred_at", "crm_activities", ["occurred_at"])

    # 5. crm_tasks
    op.create_table(
        "crm_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lead_id", sa.String(36), sa.ForeignKey("crm_leads.id", ondelete="CASCADE"), nullable=True),
        sa.Column("contact_id", sa.String(36), sa.ForeignKey("crm_contacts.id", ondelete="CASCADE"), nullable=True),
        sa.Column("assigned_to_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("priority", sa.String(32), nullable=False, server_default="medium"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_crm_tasks_tenant_lead", "crm_tasks", ["tenant_id", "lead_id"])
    op.create_index("ix_crm_tasks_due_at", "crm_tasks", ["due_at"])


def downgrade() -> None:
    op.drop_table("crm_tasks")
    op.drop_table("crm_activities")
    op.drop_table("crm_leads")
    op.drop_table("crm_pipeline_stages")
    op.drop_table("crm_contacts")
