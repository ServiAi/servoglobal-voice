"""add voice experience WebRTC runtime calls

Revision ID: 202608120001
Revises: 202608110001
"""

import sqlalchemy as sa
from alembic import op

revision = "202608120001"
down_revision = "202608110001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_voice_runtime_calls",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("context_session_id", sa.String(36), nullable=False),
        sa.Column("submission_id", sa.String(36), nullable=False),
        sa.Column("experience_id", sa.String(36), nullable=False),
        sa.Column("experience_version_id", sa.String(36), nullable=False),
        sa.Column("agent_config_id", sa.String(36), nullable=False),
        sa.Column("crm_voice_call_id", sa.String(36), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("provider_call_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("failure_code", sa.String(48), nullable=True),
        sa.Column("provider_attempt_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('reserved','starting','ready','connected','ended','failed','unknown')", name="ck_voice_runtime_status"),
        sa.CheckConstraint("failure_code IS NULL OR failure_code IN ('provider_connect_failed','provider_rejected','provider_ambiguous','provider_inconsistent','configuration_unavailable')", name="ck_voice_runtime_failure_code"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["context_session_id"], ["tenant_voice_context_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submission_id"], ["tenant_voice_experience_submissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["experience_id"], ["tenant_voice_experiences.id"]),
        sa.ForeignKeyConstraint(["experience_version_id"], ["tenant_voice_experience_versions.id"]),
        sa.ForeignKeyConstraint(["agent_config_id"], ["tenant_voice_agent_configs.id"]),
        sa.ForeignKeyConstraint(["crm_voice_call_id"], ["crm_voice_calls.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("context_session_id", name="uq_voice_runtime_context_session"),
        sa.UniqueConstraint("crm_voice_call_id", name="uq_voice_runtime_crm_call"),
    )
    op.create_index("ix_voice_runtime_tenant_status", "tenant_voice_runtime_calls", ["tenant_id", "status"])
    op.create_index("uq_voice_runtime_provider_call", "tenant_voice_runtime_calls", ["provider", "provider_call_id"], unique=True, postgresql_where=sa.text("provider_call_id IS NOT NULL"), sqlite_where=sa.text("provider_call_id IS NOT NULL"))
    op.add_column("call_events", sa.Column("dedup_key", sa.String(400), nullable=True))
    op.create_unique_constraint("uq_call_events_dedup_key", "call_events", ["dedup_key"])
    op.add_column("crm_voice_call_events", sa.Column("dedup_key", sa.String(400), nullable=True))
    op.create_unique_constraint("uq_crm_voice_call_events_dedup_key", "crm_voice_call_events", ["dedup_key"])


def downgrade() -> None:
    op.drop_constraint("uq_crm_voice_call_events_dedup_key", "crm_voice_call_events", type_="unique")
    op.drop_column("crm_voice_call_events", "dedup_key")
    op.drop_constraint("uq_call_events_dedup_key", "call_events", type_="unique")
    op.drop_column("call_events", "dedup_key")
    op.drop_index("uq_voice_runtime_provider_call", table_name="tenant_voice_runtime_calls")
    op.drop_index("ix_voice_runtime_tenant_status", table_name="tenant_voice_runtime_calls")
    op.drop_table("tenant_voice_runtime_calls")
