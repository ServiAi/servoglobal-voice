"""backfill agent_id on historical calls

Revision ID: 202608180002
Revises: 202608180001
"""

import sqlalchemy as sa
from alembic import op

revision = "202608180002"
down_revision = "202608180001"
branch_labels = None
depends_on = None


calls = sa.table(
    "calls",
    sa.column("id", sa.String),
    sa.column("tenant_id", sa.String),
    sa.column("external_provider", sa.String),
    sa.column("agent_id", sa.String),
    sa.column("provider_agent_id", sa.String),
)

agents = sa.table(
    "agents",
    sa.column("id", sa.String),
    sa.column("tenant_id", sa.String),
    sa.column("external_provider", sa.String),
    sa.column("external_agent_id", sa.String),
)


def upgrade() -> None:
    # 202608180001 mirrored tenant voice agent configs into `agents`, but
    # calls ingested before that agent row existed were already persisted
    # with agent_id=NULL and stayed "Unassigned" forever. provider_agent_id
    # on the call is the same identifier now present on the agent, so it can
    # be resolved retroactively.
    bind = op.get_bind()
    unresolved_calls = bind.execute(
        sa.select(calls.c.id, calls.c.tenant_id, calls.c.external_provider, calls.c.provider_agent_id).where(
            calls.c.agent_id.is_(None),
            calls.c.provider_agent_id.isnot(None),
        )
    ).all()
    if not unresolved_calls:
        return

    agent_by_key = {
        (row.tenant_id, row.external_provider, row.external_agent_id): row.id
        for row in bind.execute(
            sa.select(agents.c.id, agents.c.tenant_id, agents.c.external_provider, agents.c.external_agent_id).where(
                agents.c.external_agent_id.isnot(None)
            )
        ).all()
    }
    if not agent_by_key:
        return

    updates = [
        {"call_id": call.id, "agent_id": agent_id}
        for call in unresolved_calls
        if (agent_id := agent_by_key.get((call.tenant_id, call.external_provider, call.provider_agent_id)))
    ]
    if updates:
        bind.execute(
            calls.update()
            .where(calls.c.id == sa.bindparam("call_id"))
            .values(agent_id=sa.bindparam("agent_id")),
            updates,
        )


def downgrade() -> None:
    # Data backfill only; no schema change to reverse, and the rows this
    # fills in are indistinguishable from ones ingestion would have set
    # directly had the agent existed at call time. Nothing to undo.
    pass
