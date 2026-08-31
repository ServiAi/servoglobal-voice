"""whatsapp template lifecycle columns and backfill

Revision ID: 202608310001
Revises: 202608210001
"""

import sqlalchemy as sa
from alembic import op

revision = "202608310001"
down_revision = "202608210001"
branch_labels = None
depends_on = None


templates = sa.table(
    "tenant_whatsapp_templates",
    sa.column("id", sa.String),
    sa.column("template_key", sa.String),
    sa.column("status", sa.String),
    sa.column("meta_status", sa.String),
    sa.column("source", sa.String),
    sa.column("parameter_format", sa.String),
    sa.column("last_synced_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
    sa.column("variables_json", sa.JSON),
)

_DEFAULT_TEMPLATE_KEYS = ("lead_follow_up", "meeting_reminder")


def upgrade() -> None:
    op.add_column("tenant_whatsapp_templates", sa.Column("meta_status", sa.String(32), nullable=True))
    op.add_column("tenant_whatsapp_templates", sa.Column("provider_template_id", sa.String(120), nullable=True))
    op.add_column(
        "tenant_whatsapp_templates",
        sa.Column("source", sa.String(20), nullable=False, server_default="tenant_authored"),
    )
    op.add_column(
        "tenant_whatsapp_templates",
        sa.Column("parameter_format", sa.String(16), nullable=False, server_default="POSITIONAL"),
    )
    op.add_column("tenant_whatsapp_templates", sa.Column("header_json", sa.JSON(), nullable=True))
    op.add_column("tenant_whatsapp_templates", sa.Column("footer_text", sa.String(60), nullable=True))
    op.add_column(
        "tenant_whatsapp_templates",
        sa.Column("buttons_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "tenant_whatsapp_templates",
        sa.Column("components_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column("tenant_whatsapp_templates", sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.add_column(
        "tenant_whatsapp_templates", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "tenant_whatsapp_templates", sa.Column("created_by_user_id", sa.String(36), nullable=True)
    )
    op.create_foreign_key(
        "fk_tenant_whatsapp_templates_created_by_user",
        "tenant_whatsapp_templates",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Approval state used to live hidden inside variables_json (source/meta_status). Promote
    # rows already synced-and-approved from Meta into the new typed columns; everything else
    # (including the two hardcoded DEFAULT_WHATSAPP_TEMPLATES seed rows, which were never real
    # Meta templates despite showing status="active") starts as an unsent draft.
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(
            templates.c.id,
            templates.c.template_key,
            templates.c.status,
            templates.c.updated_at,
            templates.c.variables_json,
        )
    ).all()
    for row in rows:
        variables = row.variables_json or {}
        is_approved_meta_sync = (
            row.status == "active"
            and variables.get("source") == "meta_sync"
            and variables.get("meta_status") == "APPROVED"
            and row.template_key not in _DEFAULT_TEMPLATE_KEYS
        )
        if is_approved_meta_sync:
            bind.execute(
                templates.update()
                .where(templates.c.id == row.id)
                .values(
                    status="approved",
                    meta_status="APPROVED",
                    source="meta_sync",
                    parameter_format="POSITIONAL",
                    last_synced_at=row.updated_at,
                )
            )
        else:
            bind.execute(
                templates.update()
                .where(templates.c.id == row.id)
                .values(status="draft", source="tenant_authored")
            )


def downgrade() -> None:
    op.drop_constraint(
        "fk_tenant_whatsapp_templates_created_by_user", "tenant_whatsapp_templates", type_="foreignkey"
    )
    op.drop_column("tenant_whatsapp_templates", "created_by_user_id")
    op.drop_column("tenant_whatsapp_templates", "last_synced_at")
    op.drop_column("tenant_whatsapp_templates", "rejection_reason")
    op.drop_column("tenant_whatsapp_templates", "components_json")
    op.drop_column("tenant_whatsapp_templates", "buttons_json")
    op.drop_column("tenant_whatsapp_templates", "footer_text")
    op.drop_column("tenant_whatsapp_templates", "header_json")
    op.drop_column("tenant_whatsapp_templates", "parameter_format")
    op.drop_column("tenant_whatsapp_templates", "source")
    op.drop_column("tenant_whatsapp_templates", "provider_template_id")
    op.drop_column("tenant_whatsapp_templates", "meta_status")
