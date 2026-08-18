"""backfill analytics agents from tenant voice agent configs

Revision ID: 202608180001
Revises: 202608120001
"""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "202608180001"
down_revision = "202608120001"
branch_labels = None
depends_on = None


agent_configs = sa.table(
    "tenant_voice_agent_configs",
    sa.column("id", sa.String),
    sa.column("tenant_id", sa.String),
    sa.column("provider", sa.String),
    sa.column("provider_agent_id", sa.String),
    sa.column("display_name", sa.String),
    sa.column("status", sa.String),
)

agents = sa.table(
    "agents",
    sa.column("id", sa.String),
    sa.column("tenant_id", sa.String),
    sa.column("external_provider", sa.String),
    sa.column("external_agent_id", sa.String),
    sa.column("name", sa.String),
    sa.column("channel_type", sa.String),
    sa.column("status", sa.String),
)


def upgrade() -> None:
    # The analytics `agents` table is what call ingestion joins against to
    # resolve Call.agent_id, but creating/editing a voice agent config never
    # wrote a matching row there -- every call through a tenant-configured
    # agent showed up as "Unassigned". Mirror the existing configs once; new
    # ones are kept in sync by VoiceAgentService going forward.
    bind = op.get_bind()
    configs = bind.execute(
        sa.select(
            agent_configs.c.tenant_id,
            agent_configs.c.provider,
            agent_configs.c.provider_agent_id,
            agent_configs.c.display_name,
            agent_configs.c.status,
        )
    ).all()
    if not configs:
        return

    existing = {
        (row.tenant_id, row.external_provider, row.external_agent_id)
        for row in bind.execute(
            sa.select(
                agents.c.tenant_id,
                agents.c.external_provider,
                agents.c.external_agent_id,
            )
        ).all()
    }

    rows = [
        {
            "id": str(uuid.uuid4()),
            "tenant_id": config.tenant_id,
            "external_provider": config.provider,
            "external_agent_id": config.provider_agent_id,
            "name": config.display_name,
            "channel_type": "voice",
            "status": config.status,
        }
        for config in configs
        if (config.tenant_id, config.provider, config.provider_agent_id) not in existing
    ]
    if rows:
        op.bulk_insert(agents, rows)


def downgrade() -> None:
    # Data backfill only; no schema change to reverse. Rows created here are
    # indistinguishable from ones VoiceAgentService creates going forward, so
    # they are intentionally left in place.
    pass
