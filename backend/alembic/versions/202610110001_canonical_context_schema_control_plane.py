"""Canonical Context Schema / Voice Experience control plane (retire agent_config_id).

A Context Schema belongs to an Agent, not to the provider-bound legacy voice config:

* ``tenant_voice_context_schemas.agent_id`` (FK ``tenant_agents``) replaces ``agent_config_id`` and
  the lineage keys are rebuilt on it. Every schema must map to exactly ONE Agent of its tenant
  (through the legacy ``voice_agent_config_id`` link kept on the Agent versions) and agree with the
  Agent of every Experience / ExperienceVersion that references it; anything else aborts the
  migration BEFORE any legacy column is dropped. Nothing is guessed, defaulted or NULLed.
* ``tenant_voice_experiences`` and ``tenant_voice_experience_versions`` already carry the canonical
  ``agent_id`` (and the exact ``agent_version_id``) since 202610090001; their ``agent_config_id`` is
  dropped.
* ``tenant_voice_runtime_calls.agent_config_id`` stays as historical evidence of pre-#135 launches but
  becomes nullable: new rows no longer write it.

The migration is intentionally not reversible: the dropped values cannot be reconstructed
deterministically (an Agent may have had several legacy configs over its life).
"""

from alembic import op
import sqlalchemy as sa


revision = "202610110001"
down_revision = "202610100002"
branch_labels = None
depends_on = None

SCHEMAS = "tenant_voice_context_schemas"


def _fail(row_id: str, reason: str) -> RuntimeError:
    # Technical ids only: never schema keys' contents, submission values, phones or secrets.
    return RuntimeError(f"Cannot canonicalize {SCHEMAS} row {row_id}: {reason}.")


def _schema_agents(bind) -> dict[str, str]:
    """schema id -> the one Agent it belongs to, or abort."""
    agents = sa.table("tenant_agents", sa.column("id", sa.String), sa.column("tenant_id", sa.String))
    versions = sa.table(
        "tenant_agent_versions",
        sa.column("id", sa.String),
        sa.column("agent_id", sa.String),
        sa.column("tenant_id", sa.String),
        sa.column("voice_agent_config_id", sa.String),
    )
    schemas = sa.table(
        SCHEMAS, sa.column("id", sa.String), sa.column("tenant_id", sa.String), sa.column("agent_config_id", sa.String)
    )
    experiences = sa.table(
        "tenant_voice_experiences",
        sa.column("id", sa.String),
        sa.column("tenant_id", sa.String),
        sa.column("agent_id", sa.String),
        sa.column("context_schema_id", sa.String),
    )
    experience_versions = sa.table(
        "tenant_voice_experience_versions",
        sa.column("id", sa.String),
        sa.column("tenant_id", sa.String),
        sa.column("agent_id", sa.String),
        sa.column("context_schema_id", sa.String),
    )

    agent_tenants = dict(bind.execute(sa.select(agents.c.id, agents.c.tenant_id)).all())
    bindings: dict[tuple[str, str], set[str]] = {}
    for row in bind.execute(
        sa.select(versions.c.id, versions.c.agent_id, versions.c.tenant_id, versions.c.voice_agent_config_id)
    ).mappings():
        if not row["voice_agent_config_id"]:
            continue
        if agent_tenants.get(row["agent_id"]) != row["tenant_id"]:
            raise _fail(row["id"], "Agent tenant does not match its version tenant")
        bindings.setdefault((row["tenant_id"], row["voice_agent_config_id"]), set()).add(row["agent_id"])

    resolved: dict[str, str] = {}
    tenants: dict[str, str] = {}
    for row in bind.execute(sa.select(schemas.c.id, schemas.c.tenant_id, schemas.c.agent_config_id)).mappings():
        candidates = bindings.get((row["tenant_id"], row["agent_config_id"]), set())
        if not candidates:
            raise _fail(row["id"], "no canonical Agent matches its legacy voice config")
        if len(candidates) != 1:
            raise _fail(row["id"], "its legacy voice config maps to more than one Agent")
        resolved[row["id"]] = next(iter(candidates))
        tenants[row["id"]] = row["tenant_id"]

    for table in (experiences, experience_versions):
        for row in bind.execute(
            sa.select(table.c.id, table.c.tenant_id, table.c.agent_id, table.c.context_schema_id)
        ).mappings():
            schema_id = row["context_schema_id"]
            if schema_id not in resolved:
                raise _fail(schema_id, "it is referenced by a row whose schema cannot be resolved")
            if tenants[schema_id] != row["tenant_id"]:
                raise _fail(schema_id, f"it is referenced across tenants by {table.name} row {row['id']}")
            if resolved[schema_id] != row["agent_id"]:
                raise _fail(schema_id, f"its Agent disagrees with {table.name} row {row['id']}")
    return resolved


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column(SCHEMAS, sa.Column("agent_id", sa.String(36), nullable=True))

    schemas = sa.table(SCHEMAS, sa.column("id", sa.String), sa.column("agent_id", sa.String))
    for schema_id, agent_id in _schema_agents(bind).items():
        bind.execute(sa.update(schemas).where(schemas.c.id == schema_id).values(agent_id=agent_id))
    if bind.scalar(sa.select(sa.func.count()).select_from(schemas).where(schemas.c.agent_id.is_(None))):
        raise RuntimeError(f"Cannot constrain {SCHEMAS}.agent_id: null rows remain.")
    op.alter_column(SCHEMAS, "agent_id", existing_type=sa.String(36), nullable=False)

    # Rebuild every key that included the legacy column, on the canonical Agent.
    for index in (
        "uq_tenant_voice_context_schemas_draft_lineage",
        "uq_tenant_voice_context_schemas_active_lineage",
        "ix_tenant_voice_context_schemas_tenant_agent",
    ):
        op.drop_index(index, table_name=SCHEMAS)
    op.drop_constraint("uq_tenant_voice_context_schemas_lineage_version", SCHEMAS, type_="unique")
    op.create_unique_constraint(
        "uq_tenant_voice_context_schemas_lineage_version",
        SCHEMAS,
        ["tenant_id", "agent_id", "schema_key", "version"],
    )
    op.create_index("ix_tenant_voice_context_schemas_tenant_agent", SCHEMAS, ["tenant_id", "agent_id"])
    for status, name in (("active", "active"), ("draft", "draft")):
        op.create_index(
            f"uq_tenant_voice_context_schemas_{name}_lineage",
            SCHEMAS,
            ["tenant_id", "agent_id", "schema_key"],
            unique=True,
            postgresql_where=sa.text(f"status = '{status}'"),
            sqlite_where=sa.text(f"status = '{status}'"),
        )
    op.create_foreign_key(
        "fk_tenant_voice_context_schemas_agent", SCHEMAS, "tenant_agents", ["agent_id"], ["id"], ondelete="CASCADE"
    )
    op.drop_column(SCHEMAS, "agent_config_id")

    op.drop_index("ix_tenant_voice_experiences_tenant_agent", table_name="tenant_voice_experiences")
    op.drop_column("tenant_voice_experiences", "agent_config_id")
    op.drop_column("tenant_voice_experience_versions", "agent_config_id")

    op.alter_column("tenant_voice_runtime_calls", "agent_config_id", existing_type=sa.String(36), nullable=True)


def downgrade() -> None:
    raise RuntimeError(
        "202610110001 is not reversible: the legacy agent_config_id values it drops cannot be "
        "reconstructed deterministically from the canonical Agent binding. Restore from backup."
    )
