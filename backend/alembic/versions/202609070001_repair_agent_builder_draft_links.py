"""repair agent builder draft links: backfill missing draft_version_id

Revision ID: 202609070001
Revises: 202609060001
"""

import sqlalchemy as sa

from alembic import op

revision = "202609070001"
down_revision = "202609060001"
branch_labels = None
depends_on = None


tenant_agents = sa.table(
    "tenant_agents",
    sa.column("id", sa.String),
    sa.column("tenant_id", sa.String),
    sa.column("status", sa.String),
    sa.column("draft_version_id", sa.String),
)

tenant_agent_versions = sa.table(
    "tenant_agent_versions",
    sa.column("id", sa.String),
    sa.column("agent_id", sa.String),
    sa.column("tenant_id", sa.String),
    sa.column("status", sa.String),
)


def upgrade() -> None:
    _repair_missing_draft_links()


def _repair_missing_draft_links() -> None:
    # Fixes agents produced by the original 202609060001 backfill: every
    # TenantVoiceAgentConfig with status != "active" became a draft
    # TenantAgent + draft TenantAgentVersion, but that migration never wrote
    # tenant_agents.draft_version_id (the column wasn't even in its insert
    # table), so those agents are stuck without a recoverable draft via
    # GET /api/v1/agents/{agent_id}/draft. Idempotent: only touches agents
    # that still have status="draft" AND draft_version_id IS NULL, and only
    # when exactly one draft version can be matched deterministically.
    bind = op.get_bind()
    broken_agents = bind.execute(
        sa.select(tenant_agents.c.id, tenant_agents.c.tenant_id).where(
            tenant_agents.c.status == "draft",
            tenant_agents.c.draft_version_id.is_(None),
        )
    ).all()
    if not broken_agents:
        return

    updates = []
    for agent in broken_agents:
        draft_versions = bind.execute(
            sa.select(tenant_agent_versions.c.id).where(
                tenant_agent_versions.c.agent_id == agent.id,
                tenant_agent_versions.c.tenant_id == agent.tenant_id,
                tenant_agent_versions.c.status == "draft",
            )
        ).all()
        if len(draft_versions) != 1:
            # Fall closed: no draft version (nothing to link) or more than
            # one (ambiguous -- can't guess which one is "the" draft).
            # Leaving draft_version_id NULL keeps the inconsistency visible
            # via GET /draft returning 409 rather than silently picking one.
            print(
                f"[202609070001] skipping agent {agent.id}: found "
                f"{len(draft_versions)} draft version(s), expected exactly 1"
            )
            continue
        updates.append({"agent_id": agent.id, "version_id": draft_versions[0].id})

    if updates:
        bind.execute(
            sa.update(tenant_agents)
            .where(tenant_agents.c.id == sa.bindparam("agent_id"))
            .values(draft_version_id=sa.bindparam("version_id")),
            updates,
        )


def downgrade() -> None:
    # Data repair only; the affected agents' draft_version_id could
    # legitimately have been NULL before, but re-nulling a now-correct
    # pointer isn't a safe inverse (it would just reintroduce the bug). No-op.
    pass
