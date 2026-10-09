"""Bind Voice Experiences to canonical Agents and exact published versions."""

from alembic import op
import sqlalchemy as sa


revision = "202610090001"
down_revision = "202610080001"
branch_labels = None
depends_on = None


def _fail(table_name: str, row_id: str, reason: str) -> RuntimeError:
    return RuntimeError(f"Cannot backfill {table_name} row {row_id}: {reason}.")


def _legacy_agent_id(*, table_name: str, row_id: str, tenant_id: str, config_id: str, bindings):
    candidates = bindings.get((tenant_id, config_id), set())
    if not candidates:
        raise _fail(table_name, row_id, "legacy agent binding not found")
    if len(candidates) != 1:
        raise _fail(table_name, row_id, "legacy agent binding is ambiguous")
    return next(iter(candidates))


def _exact_agent_version(*, table_name: str, row_id: str, published_at, candidates):
    if published_at is None:
        raise _fail(table_name, row_id, "experience publication timestamp is missing")
    if not candidates:
        raise _fail(table_name, row_id, "no published AgentVersion matches the legacy binding")
    earlier = [candidate for candidate in candidates if candidate[1] <= published_at]
    selected_at = max((candidate[1] for candidate in earlier), default=None)
    if selected_at is None:
        selected_at = min(candidate[1] for candidate in candidates)
    selected = [candidate for candidate in candidates if candidate[1] == selected_at]
    if len(selected) != 1:
        raise _fail(table_name, row_id, "AgentVersion timestamp does not identify one snapshot")
    return selected[0][0]


def upgrade() -> None:
    op.add_column("tenant_voice_experiences", sa.Column("agent_id", sa.String(36), nullable=True))
    op.add_column("tenant_voice_experience_versions", sa.Column("agent_id", sa.String(36), nullable=True))
    op.add_column("tenant_voice_experience_versions", sa.Column("agent_version_id", sa.String(36), nullable=True))

    op.create_foreign_key(
        "fk_tenant_voice_experiences_agent",
        "tenant_voice_experiences",
        "tenant_agents",
        ["agent_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_tenant_voice_experience_versions_agent",
        "tenant_voice_experience_versions",
        "tenant_agents",
        ["agent_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_tenant_voice_experience_versions_agent_version",
        "tenant_voice_experience_versions",
        "tenant_agent_versions",
        ["agent_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    bind = op.get_bind()
    experiences = sa.table(
        "tenant_voice_experiences",
        sa.column("id", sa.String),
        sa.column("tenant_id", sa.String),
        sa.column("agent_config_id", sa.String),
        sa.column("agent_id", sa.String),
    )
    experience_versions = sa.table(
        "tenant_voice_experience_versions",
        sa.column("id", sa.String),
        sa.column("tenant_id", sa.String),
        sa.column("agent_config_id", sa.String),
        sa.column("published_at", sa.DateTime(timezone=True)),
        sa.column("agent_id", sa.String),
        sa.column("agent_version_id", sa.String),
    )
    agent_versions = sa.table(
        "tenant_agent_versions",
        sa.column("id", sa.String),
        sa.column("agent_id", sa.String),
        sa.column("tenant_id", sa.String),
        sa.column("status", sa.String),
        sa.column("voice_agent_config_id", sa.String),
        sa.column("published_at", sa.DateTime(timezone=True)),
    )
    agents = sa.table(
        "tenant_agents",
        sa.column("id", sa.String),
        sa.column("tenant_id", sa.String),
    )

    agent_tenants = dict(bind.execute(sa.select(agents.c.id, agents.c.tenant_id)).all())
    bindings: dict[tuple[str, str], set[str]] = {}
    exact_versions: dict[tuple[str, str, str], list[tuple[str, object]]] = {}
    for row in bind.execute(sa.select(
        agent_versions.c.id,
        agent_versions.c.agent_id,
        agent_versions.c.tenant_id,
        agent_versions.c.status,
        agent_versions.c.voice_agent_config_id,
        agent_versions.c.published_at,
    )).mappings():
        config_id = row["voice_agent_config_id"]
        tenant_id = row["tenant_id"]
        agent_id = row["agent_id"]
        if not config_id:
            continue
        if agent_tenants.get(agent_id) != tenant_id:
            raise _fail("tenant_agent_versions", row["id"], "Agent tenant does not match version tenant")
        bindings.setdefault((tenant_id, config_id), set()).add(agent_id)
        if row["status"] in {"published", "superseded"} and row["published_at"] is not None:
            exact_versions.setdefault((tenant_id, agent_id, config_id), []).append(
                (row["id"], row["published_at"])
            )

    for row in bind.execute(sa.select(
        experiences.c.id, experiences.c.tenant_id, experiences.c.agent_config_id
    )).mappings():
        agent_id = _legacy_agent_id(
            table_name="tenant_voice_experiences",
            row_id=row["id"],
            tenant_id=row["tenant_id"],
            config_id=row["agent_config_id"],
            bindings=bindings,
        )
        bind.execute(
            sa.update(experiences).where(experiences.c.id == row["id"]).values(agent_id=agent_id)
        )

    for row in bind.execute(sa.select(
        experience_versions.c.id,
        experience_versions.c.tenant_id,
        experience_versions.c.agent_config_id,
        experience_versions.c.published_at,
    )).mappings():
        agent_id = _legacy_agent_id(
            table_name="tenant_voice_experience_versions",
            row_id=row["id"],
            tenant_id=row["tenant_id"],
            config_id=row["agent_config_id"],
            bindings=bindings,
        )
        agent_version_id = _exact_agent_version(
            table_name="tenant_voice_experience_versions",
            row_id=row["id"],
            published_at=row["published_at"],
            candidates=exact_versions.get((row["tenant_id"], agent_id, row["agent_config_id"]), []),
        )
        bind.execute(
            sa.update(experience_versions)
            .where(experience_versions.c.id == row["id"])
            .values(agent_id=agent_id, agent_version_id=agent_version_id)
        )

    for table_name, column_names in (
        ("tenant_voice_experiences", ("agent_id",)),
        ("tenant_voice_experience_versions", ("agent_id", "agent_version_id")),
    ):
        table = sa.table(table_name, *(sa.column(name) for name in column_names))
        for column_name in column_names:
            if bind.scalar(sa.select(sa.func.count()).select_from(table).where(table.c[column_name].is_(None))):
                raise RuntimeError(f"Cannot constrain {table_name}.{column_name}: null rows remain.")

    op.alter_column("tenant_voice_experiences", "agent_id", nullable=False)
    op.alter_column("tenant_voice_experience_versions", "agent_id", nullable=False)
    op.alter_column("tenant_voice_experience_versions", "agent_version_id", nullable=False)
    op.create_index(
        "ix_tenant_voice_experiences_tenant_agent_id",
        "tenant_voice_experiences",
        ["tenant_id", "agent_id"],
    )
    op.create_index(
        "ix_tenant_voice_experience_versions_tenant_agent",
        "tenant_voice_experience_versions",
        ["tenant_id", "agent_id"],
    )
    op.create_index(
        "ix_tenant_voice_experience_versions_agent_version",
        "tenant_voice_experience_versions",
        ["agent_version_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_voice_experience_versions_agent_version", table_name="tenant_voice_experience_versions")
    op.drop_index("ix_tenant_voice_experience_versions_tenant_agent", table_name="tenant_voice_experience_versions")
    op.drop_index("ix_tenant_voice_experiences_tenant_agent_id", table_name="tenant_voice_experiences")
    op.drop_constraint(
        "fk_tenant_voice_experience_versions_agent_version",
        "tenant_voice_experience_versions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_tenant_voice_experience_versions_agent",
        "tenant_voice_experience_versions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_tenant_voice_experiences_agent",
        "tenant_voice_experiences",
        type_="foreignkey",
    )
    op.drop_column("tenant_voice_experience_versions", "agent_version_id")
    op.drop_column("tenant_voice_experience_versions", "agent_id")
    op.drop_column("tenant_voice_experiences", "agent_id")
