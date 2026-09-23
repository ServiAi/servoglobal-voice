"""custom http tools foundation: tenant_tools, tenant_http_tool_configs, tenant_tool_credentials

Revision ID: 202609220001
Revises: 202609150001
"""

import sqlalchemy as sa

from alembic import op

revision = "202609220001"
down_revision = "202609150001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_tools",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=90), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="disabled"),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("key LIKE 'custom.%'", name="ck_tenant_tools_key_namespace"),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_tenant_tools_status"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "key", name="uq_tenant_tools_tenant_key"),
    )
    op.create_index("ix_tenant_tools_tenant_id", "tenant_tools", ["tenant_id"])
    op.create_index("ix_tenant_tools_tenant_status", "tenant_tools", ["tenant_id", "status"])

    op.create_table(
        "tenant_http_tool_configs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_tool_id", sa.String(length=36), nullable=False),
        sa.Column("method", sa.String(length=8), nullable=False),
        sa.Column("base_url", sa.String(length=2048), nullable=False),
        sa.Column("path_template", sa.String(length=1024), nullable=False, server_default="/"),
        sa.Column("timeout_ms", sa.Integer(), nullable=False, server_default="8000"),
        sa.Column("headers_json", sa.JSON(), nullable=False),
        sa.Column("path_mapping_json", sa.JSON(), nullable=False),
        sa.Column("query_mapping_json", sa.JSON(), nullable=False),
        sa.Column("body_mapping_json", sa.JSON(), nullable=False),
        sa.Column("input_schema_json", sa.JSON(), nullable=False),
        sa.Column("response_mapping_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "method IN ('GET', 'POST', 'PUT', 'PATCH', 'DELETE')",
            name="ck_tenant_http_tool_configs_method",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_tool_id"], ["tenant_tools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_tool_id", name="uq_tenant_http_tool_configs_tenant_tool"),
    )
    op.create_index(
        "ix_tenant_http_tool_configs_tenant_tool",
        "tenant_http_tool_configs",
        ["tenant_id", "tenant_tool_id"],
    )

    op.create_table(
        "tenant_tool_credentials",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_tool_id", sa.String(length=36), nullable=False),
        sa.Column("auth_type", sa.String(length=16), nullable=False, server_default="none"),
        sa.Column("api_key_header_name", sa.String(length=80), nullable=True),
        sa.Column("secrets_json_encrypted", sa.Text(), nullable=True),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "auth_type IN ('none', 'bearer', 'api_key', 'basic')",
            name="ck_tenant_tool_credentials_auth_type",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_tool_id"], ["tenant_tools.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rotated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_tool_id", name="uq_tenant_tool_credentials_tenant_tool"),
    )
    op.create_index(
        "ix_tenant_tool_credentials_tenant_tool",
        "tenant_tool_credentials",
        ["tenant_id", "tenant_tool_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_tool_credentials_tenant_tool", table_name="tenant_tool_credentials")
    op.drop_table("tenant_tool_credentials")
    op.drop_index("ix_tenant_http_tool_configs_tenant_tool", table_name="tenant_http_tool_configs")
    op.drop_table("tenant_http_tool_configs")
    op.drop_index("ix_tenant_tools_tenant_status", table_name="tenant_tools")
    op.drop_index("ix_tenant_tools_tenant_id", table_name="tenant_tools")
    op.drop_table("tenant_tools")
