"""add tenant voice experiences and immutable published versions

Revision ID: 202608050002
Revises: 202608050001
"""

import sqlalchemy as sa

from alembic import op

revision = "202608050002"
down_revision = "202608050001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_voice_experiences",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("agent_config_id", sa.String(length=36), nullable=False),
        sa.Column("context_schema_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("default_locale", sa.String(length=16), nullable=False, server_default="es"),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("theme_json", sa.JSON(), nullable=False),
        sa.Column("consent_json", sa.JSON(), nullable=False),
        sa.Column("call_settings_json", sa.JSON(), nullable=False),
        sa.Column("published_version_id", sa.String(length=36), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'unpublished', 'archived')",
            name="ck_tenant_voice_experiences_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_config_id"], ["tenant_voice_agent_configs.id"]),
        sa.ForeignKeyConstraint(["context_schema_id"], ["tenant_voice_context_schemas.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_tenant_voice_experiences_slug"),
    )
    op.create_index(
        "ix_tenant_voice_experiences_tenant_status",
        "tenant_voice_experiences",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_tenant_voice_experiences_tenant_agent",
        "tenant_voice_experiences",
        ["tenant_id", "agent_config_id"],
    )
    op.create_index(
        "ix_tenant_voice_experiences_slug", "tenant_voice_experiences", ["slug"]
    )

    op.create_table(
        "tenant_voice_experience_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("experience_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("agent_config_id", sa.String(length=36), nullable=False),
        sa.Column("context_schema_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("default_locale", sa.String(length=16), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("theme_json", sa.JSON(), nullable=False),
        sa.Column("consent_json", sa.JSON(), nullable=False),
        sa.Column("call_settings_json", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["experience_id"], ["tenant_voice_experiences.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_config_id"], ["tenant_voice_agent_configs.id"]),
        sa.ForeignKeyConstraint(["context_schema_id"], ["tenant_voice_context_schemas.id"]),
        sa.ForeignKeyConstraint(
            ["published_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "experience_id",
            "version",
            name="uq_tenant_voice_experience_versions_experience_version",
        ),
    )
    op.create_index(
        "ix_tenant_voice_experience_versions_tenant",
        "tenant_voice_experience_versions",
        ["tenant_id"],
    )
    op.create_index(
        "ix_tenant_voice_experience_versions_experience",
        "tenant_voice_experience_versions",
        ["experience_id"],
    )
    with op.batch_alter_table("tenant_voice_experiences") as batch_op:
        batch_op.create_foreign_key(
            "fk_tenant_voice_experiences_published_version",
            "tenant_voice_experience_versions",
            ["published_version_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("tenant_voice_experiences") as batch_op:
        batch_op.drop_constraint(
            "fk_tenant_voice_experiences_published_version", type_="foreignkey"
        )
    op.drop_index(
        "ix_tenant_voice_experience_versions_experience",
        table_name="tenant_voice_experience_versions",
    )
    op.drop_index(
        "ix_tenant_voice_experience_versions_tenant",
        table_name="tenant_voice_experience_versions",
    )
    op.drop_table("tenant_voice_experience_versions")
    op.drop_index("ix_tenant_voice_experiences_slug", table_name="tenant_voice_experiences")
    op.drop_index(
        "ix_tenant_voice_experiences_tenant_agent",
        table_name="tenant_voice_experiences",
    )
    op.drop_index(
        "ix_tenant_voice_experiences_tenant_status",
        table_name="tenant_voice_experiences",
    )
    op.drop_table("tenant_voice_experiences")
