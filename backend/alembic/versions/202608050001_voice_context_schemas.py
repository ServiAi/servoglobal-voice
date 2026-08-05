"""add tenant voice context schemas

Revision ID: 202608050001
Revises: 202608040001
"""

from alembic import op
import sqlalchemy as sa


revision = "202608050001"
down_revision = "202608040001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_voice_context_schemas",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("agent_config_id", sa.String(length=36), nullable=False),
        sa.Column("schema_key", sa.String(length=80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["agent_config_id"], ["tenant_voice_agent_configs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "agent_config_id",
            "schema_key",
            "version",
            name="uq_tenant_voice_context_schemas_lineage_version",
        ),
    )
    op.create_index(
        "ix_tenant_voice_context_schemas_tenant_agent",
        "tenant_voice_context_schemas",
        ["tenant_id", "agent_config_id"],
    )
    op.create_index(
        "ix_tenant_voice_context_schemas_tenant_key",
        "tenant_voice_context_schemas",
        ["tenant_id", "schema_key"],
    )
    op.create_index(
        "ix_tenant_voice_context_schemas_tenant_status",
        "tenant_voice_context_schemas",
        ["tenant_id", "status"],
    )

    op.create_table(
        "tenant_voice_context_fields",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("schema_id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("field_type", sa.String(length=20), nullable=False),
        sa.Column("collection_mode", sa.String(length=24), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("sensitivity", sa.String(length=16), nullable=False, server_default="standard"),
        sa.Column("validation_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("options_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["schema_id"], ["tenant_voice_context_schemas.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "schema_id", "key", name="uq_tenant_voice_context_fields_schema_key"
        ),
    )
    op.create_index(
        "ix_tenant_voice_context_fields_tenant_schema",
        "tenant_voice_context_fields",
        ["tenant_id", "schema_id"],
    )
    op.create_index(
        "ix_tenant_voice_context_fields_schema_position",
        "tenant_voice_context_fields",
        ["schema_id", "position"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tenant_voice_context_fields_schema_position",
        table_name="tenant_voice_context_fields",
    )
    op.drop_index(
        "ix_tenant_voice_context_fields_tenant_schema",
        table_name="tenant_voice_context_fields",
    )
    op.drop_table("tenant_voice_context_fields")
    op.drop_index(
        "ix_tenant_voice_context_schemas_tenant_status",
        table_name="tenant_voice_context_schemas",
    )
    op.drop_index(
        "ix_tenant_voice_context_schemas_tenant_key",
        table_name="tenant_voice_context_schemas",
    )
    op.drop_index(
        "ix_tenant_voice_context_schemas_tenant_agent",
        table_name="tenant_voice_context_schemas",
    )
    op.drop_table("tenant_voice_context_schemas")
