"""agent builder foundation: tenant_agents, tenant_agent_versions, backfill

Revision ID: 202609060001
Revises: 202609050001
"""

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa

from alembic import op

revision = "202609060001"
down_revision = "202609050001"
branch_labels = None
depends_on = None


agent_configs = sa.table(
    "tenant_voice_agent_configs",
    sa.column("id", sa.String),
    sa.column("tenant_id", sa.String),
    sa.column("provider", sa.String),
    sa.column("display_name", sa.String),
    sa.column("description", sa.String),
    sa.column("purpose", sa.String),
    sa.column("default_language", sa.String),
    sa.column("default_timezone", sa.String),
    sa.column("default_system_prompt", sa.String),
    sa.column("status", sa.String),
)

tenant_agents = sa.table(
    "tenant_agents",
    sa.column("id", sa.String),
    sa.column("tenant_id", sa.String),
    sa.column("name", sa.String),
    sa.column("description", sa.String),
    sa.column("status", sa.String),
    sa.column("published_version_id", sa.String),
    sa.column("created_at", sa.DateTime),
    sa.column("updated_at", sa.DateTime),
)

tenant_agent_versions = sa.table(
    "tenant_agent_versions",
    sa.column("id", sa.String),
    sa.column("agent_id", sa.String),
    sa.column("tenant_id", sa.String),
    sa.column("version", sa.Integer),
    sa.column("status", sa.String),
    sa.column("language", sa.String),
    sa.column("timezone", sa.String),
    sa.column("identity_json", sa.JSON),
    sa.column("instructions_json", sa.JSON),
    sa.column("behavior_json", sa.JSON),
    sa.column("runtime_binding_json", sa.JSON),
    sa.column("voice_agent_config_id", sa.String),
    sa.column("published_at", sa.DateTime),
    sa.column("created_at", sa.DateTime),
)


def upgrade() -> None:
    op.create_table(
        "tenant_agents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("published_version_id", sa.String(length=36), nullable=True),
        sa.Column("draft_version_id", sa.String(length=36), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'archived')",
            name="ck_tenant_agents_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tenant_agents_tenant_status", "tenant_agents", ["tenant_id", "status"]
    )

    op.create_table(
        "tenant_agent_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("language", sa.String(length=16), nullable=False, server_default="es"),
        sa.Column("timezone", sa.String(length=80), nullable=False, server_default="America/Bogota"),
        sa.Column("identity_json", sa.JSON(), nullable=False),
        sa.Column("instructions_json", sa.JSON(), nullable=False),
        sa.Column("behavior_json", sa.JSON(), nullable=False),
        sa.Column("runtime_binding_json", sa.JSON(), nullable=False),
        sa.Column("voice_agent_config_id", sa.String(length=36), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'superseded')",
            name="ck_tenant_agent_versions_status",
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["tenant_agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["voice_agent_config_id"], ["tenant_voice_agent_configs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "agent_id", "version", name="uq_tenant_agent_versions_agent_version"
        ),
    )
    op.create_index(
        "ix_tenant_agent_versions_tenant", "tenant_agent_versions", ["tenant_id"]
    )
    op.create_index(
        "ix_tenant_agent_versions_agent", "tenant_agent_versions", ["agent_id"]
    )

    with op.batch_alter_table("tenant_agents") as batch_op:
        batch_op.create_foreign_key(
            "fk_tenant_agents_published_version",
            "tenant_agent_versions",
            ["published_version_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_tenant_agents_draft_version",
            "tenant_agent_versions",
            ["draft_version_id"],
            ["id"],
            ondelete="SET NULL",
        )

    _backfill_from_voice_agent_configs()


def _backfill_from_voice_agent_configs() -> None:
    # Every existing TenantVoiceAgentConfig becomes a TenantAgent with a
    # single published v1 version that links back via voice_agent_config_id.
    # `default_voice` and `default_tools_json` intentionally stay on
    # TenantVoiceAgentConfig only for now -- they are not duplicated here to
    # avoid two sources of truth before the Model/Capability Registry exists.
    bind = op.get_bind()
    configs = bind.execute(
        sa.select(
            agent_configs.c.id,
            agent_configs.c.tenant_id,
            agent_configs.c.provider,
            agent_configs.c.display_name,
            agent_configs.c.description,
            agent_configs.c.purpose,
            agent_configs.c.default_language,
            agent_configs.c.default_timezone,
            agent_configs.c.default_system_prompt,
            agent_configs.c.status,
        )
    ).all()
    if not configs:
        return

    now = datetime.now(timezone.utc)
    agent_rows = []
    version_rows = []
    for config in configs:
        agent_id = str(uuid.uuid4())
        version_id = str(uuid.uuid4())
        agent_status = "active" if config.status == "active" else "draft"
        agent_rows.append(
            {
                "id": agent_id,
                "tenant_id": config.tenant_id,
                "name": config.display_name,
                "description": config.description,
                "status": agent_status,
                "published_version_id": version_id if agent_status == "active" else None,
                "created_at": now,
                "updated_at": now,
            }
        )
        version_rows.append(
            {
                "id": version_id,
                "agent_id": agent_id,
                "tenant_id": config.tenant_id,
                "version": 1,
                "status": "published" if agent_status == "active" else "draft",
                "language": config.default_language or "es",
                "timezone": config.default_timezone or "America/Bogota",
                "identity_json": {
                    "name": config.display_name,
                    "description": config.description,
                },
                "instructions_json": {
                    "role": config.purpose,
                    "objective": "",
                    "system_prompt": config.default_system_prompt,
                    "greeting": "",
                    "closing": "",
                },
                "behavior_json": {
                    "response_style": "balanced",
                    "interruptions": "balanced",
                    "turn_detection": "automatic",
                    "confirmation_strategy": "important_data",
                    "agent_first": True,
                },
                "runtime_binding_json": {
                    "pipeline_type": "realtime",
                    "realtime": {"provider": config.provider, "model": config.provider},
                },
                "voice_agent_config_id": config.id,
                "published_at": now if agent_status == "active" else None,
                "created_at": now,
            }
        )

    op.bulk_insert(tenant_agents, agent_rows)
    op.bulk_insert(tenant_agent_versions, version_rows)


def downgrade() -> None:
    with op.batch_alter_table("tenant_agents") as batch_op:
        batch_op.drop_constraint("fk_tenant_agents_draft_version", type_="foreignkey")
        batch_op.drop_constraint("fk_tenant_agents_published_version", type_="foreignkey")
    op.drop_index("ix_tenant_agent_versions_agent", table_name="tenant_agent_versions")
    op.drop_index("ix_tenant_agent_versions_tenant", table_name="tenant_agent_versions")
    op.drop_table("tenant_agent_versions")
    op.drop_index("ix_tenant_agents_tenant_status", table_name="tenant_agents")
    op.drop_table("tenant_agents")
