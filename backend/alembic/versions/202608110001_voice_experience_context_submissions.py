"""add voice experience context submissions

Revision ID: 202608110001
Revises: 202608050003
"""

import sqlalchemy as sa

from alembic import op


revision = "202608110001"
down_revision = "202608050003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_voice_experience_submissions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("experience_id", sa.String(length=36), nullable=False),
        sa.Column("experience_version_id", sa.String(length=36), nullable=False),
        sa.Column("context_schema_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("crm_contact_id", sa.String(length=36), nullable=True),
        sa.Column("crm_lead_id", sa.String(length=36), nullable=True),
        sa.Column("consent_accepted", sa.Boolean(), nullable=False),
        sa.Column("consent_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(consent_accepted = true AND consent_accepted_at IS NOT NULL) OR "
            "(consent_accepted = false AND consent_accepted_at IS NULL)",
            name="ck_voice_submissions_consent_evidence",
        ),
        sa.CheckConstraint("locale IN ('es', 'en')", name="ck_voice_submissions_locale"),
        sa.ForeignKeyConstraint(["crm_contact_id"], ["crm_contacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["crm_lead_id"], ["crm_leads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["context_schema_id"], ["tenant_voice_context_schemas.id"]),
        sa.ForeignKeyConstraint(["experience_id"], ["tenant_voice_experiences.id"]),
        sa.ForeignKeyConstraint(
            ["experience_version_id"], ["tenant_voice_experience_versions.id"]
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_voice_submissions_tenant_created",
        "tenant_voice_experience_submissions",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_voice_submissions_experience",
        "tenant_voice_experience_submissions",
        ["experience_id"],
    )

    op.create_table(
        "tenant_voice_experience_submission_values",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("field_key", sa.String(length=80), nullable=False),
        sa.Column("field_type", sa.String(length=20), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["tenant_voice_experience_submissions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "submission_id", "field_key", name="uq_voice_submission_values_field"
        ),
    )
    op.create_index(
        "ix_voice_submission_values_submission",
        "tenant_voice_experience_submission_values",
        ["submission_id"],
    )

    op.create_table(
        "tenant_voice_context_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("experience_id", sa.String(length=36), nullable=False),
        sa.Column("experience_version_id", sa.String(length=36), nullable=False),
        sa.Column("context_schema_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'consumed', 'expired')",
            name="ck_voice_context_sessions_status",
        ),
        sa.ForeignKeyConstraint(["context_schema_id"], ["tenant_voice_context_schemas.id"]),
        sa.ForeignKeyConstraint(["experience_id"], ["tenant_voice_experiences.id"]),
        sa.ForeignKeyConstraint(
            ["experience_version_id"], ["tenant_voice_experience_versions.id"]
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["tenant_voice_experience_submissions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "submission_id", name="uq_voice_context_sessions_submission"
        ),
        sa.UniqueConstraint("token_hash", name="uq_voice_context_sessions_token_hash"),
    )
    op.create_index(
        "ix_voice_context_sessions_tenant_expires",
        "tenant_voice_context_sessions",
        ["tenant_id", "expires_at"],
    )
    op.create_table(
        "voice_public_rate_limit_windows",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=160), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scope", "window_start", name="uq_voice_rate_windows_scope_start"
        ),
    )
    op.create_index(
        "ix_voice_rate_windows_window_start",
        "voice_public_rate_limit_windows",
        ["window_start"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_voice_rate_windows_window_start", table_name="voice_public_rate_limit_windows"
    )
    op.drop_table("voice_public_rate_limit_windows")
    op.drop_index(
        "ix_voice_context_sessions_tenant_expires", table_name="tenant_voice_context_sessions"
    )
    op.drop_table("tenant_voice_context_sessions")
    op.drop_index(
        "ix_voice_submission_values_submission",
        table_name="tenant_voice_experience_submission_values",
    )
    op.drop_table("tenant_voice_experience_submission_values")
    op.drop_index(
        "ix_voice_submissions_experience",
        table_name="tenant_voice_experience_submissions",
    )
    op.drop_index(
        "ix_voice_submissions_tenant_created",
        table_name="tenant_voice_experience_submissions",
    )
    op.drop_table("tenant_voice_experience_submissions")
