"""Module 12 Evaluations core."""

from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone

revision = "202610070001"
down_revision = "202610050001"
branch_labels = None
depends_on = None

_SYSTEM_KEY = "__system__"
_DEFINITION_ID = "00000000-0000-4000-8000-000000000012"
_VERSION_ID = "00000000-0000-4000-8000-000000000013"
_CRITERIA = [
    {"key": "session_terminal", "evaluator_type": "deterministic", "weight": 1},
    {"key": "runtime_health", "evaluator_type": "deterministic", "weight": 1},
    {"key": "tool_execution_health", "evaluator_type": "deterministic", "weight": 1},
]


def upgrade() -> None:
    op.create_table(
        "evaluation_definitions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_scope", sa.String(16), nullable=False),
        sa.Column("owner_key", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("definition_key", sa.String(100), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "(owner_scope = 'system' AND tenant_id IS NULL AND owner_key = '__system__') OR "
            "(owner_scope = 'tenant' AND tenant_id IS NOT NULL AND owner_key = tenant_id)",
            name="ck_evaluation_definitions_owner",
        ),
        sa.UniqueConstraint("id", "owner_key", name="uq_evaluation_definitions_id_owner"),
        sa.UniqueConstraint("owner_key", "definition_key", name="uq_evaluation_definitions_owner_key"),
    )
    op.create_index("ix_evaluation_definitions_tenant", "evaluation_definitions", ["tenant_id"])

    op.create_table(
        "evaluation_definition_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("definition_id", sa.String(36), nullable=False),
        sa.Column("owner_key", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("criteria_json", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("version > 0", name="ck_evaluation_definition_versions_version"),
        sa.CheckConstraint("status IN ('draft','published','superseded')", name="ck_evaluation_definition_versions_status"),
        sa.ForeignKeyConstraint(
            ["definition_id", "owner_key"],
            ["evaluation_definitions.id", "evaluation_definitions.owner_key"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("definition_id", "version", name="uq_evaluation_definition_versions_number"),
        sa.UniqueConstraint("id", "owner_key", name="uq_evaluation_definition_versions_id_owner"),
    )
    op.create_index(
        "ix_evaluation_definition_versions_published",
        "evaluation_definition_versions", ["owner_key", "status", "definition_id"],
    )

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_key", sa.String(36), nullable=False),
        sa.Column("subject_type", sa.String(40), nullable=False),
        sa.Column("subject_id", sa.String(100), nullable=False),
        sa.Column("agent_version_id", sa.String(36), nullable=True),
        sa.Column("definition_version_id", sa.String(36), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("trigger_key", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("conflict_detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("conflicting_evidence_hash", sa.String(64), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("claim_token", sa.String(64), nullable=True),
        sa.Column("claim_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(80), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("owner_key = '__system__' OR owner_key = tenant_id", name="ck_evaluation_runs_definition_owner"),
        sa.CheckConstraint("status IN ('queued','running','completed','failed','cancelled')", name="ck_evaluation_runs_status"),
        sa.CheckConstraint("subject_type <> '' AND subject_id <> '' AND trigger_key <> ''", name="ck_evaluation_runs_identity"),
        sa.CheckConstraint("attempt_count >= 0 AND claim_generation >= 0", name="ck_evaluation_runs_claim_counts"),
        sa.CheckConstraint("score IS NULL OR score BETWEEN 0 AND 100", name="ck_evaluation_runs_score"),
        sa.ForeignKeyConstraint(
            ["definition_version_id", "owner_key"],
            ["evaluation_definition_versions.id", "evaluation_definition_versions.owner_key"],
        ),
        sa.UniqueConstraint(
            "tenant_id", "subject_type", "subject_id", "definition_version_id", "trigger_key",
            name="uq_evaluation_runs_identity",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_evaluation_runs_tenant_id"),
    )
    op.create_index("ix_evaluation_runs_due", "evaluation_runs", ["status", "next_attempt_at", "requested_at"])
    op.create_index("ix_evaluation_runs_subject", "evaluation_runs", ["tenant_id", "subject_type", "subject_id"])

    op.create_table(
        "evaluation_criterion_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("criterion_key", sa.String(100), nullable=False),
        sa.Column("evaluator_type", sa.String(20), nullable=False, server_default="deterministic"),
        sa.Column("implementation_version", sa.String(40), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("evidence_ref_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("evaluator_type IN ('deterministic','llm','human')", name="ck_evaluation_criterion_results_evaluator"),
        sa.CheckConstraint("score IS NULL OR score BETWEEN 0 AND 100", name="ck_evaluation_criterion_results_score"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"], ["evaluation_runs.tenant_id", "evaluation_runs.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("tenant_id", "run_id", "criterion_key", name="uq_evaluation_criterion_results_key"),
    )
    op.create_index("ix_evaluation_criterion_results_run", "evaluation_criterion_results", ["tenant_id", "run_id"])

    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_published_evaluation_version_mutation() RETURNS trigger AS $$
        BEGIN
            IF OLD.status = 'published' THEN
                RAISE EXCEPTION 'published_evaluation_definition_version_is_immutable';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_published_evaluation_version_immutable
        BEFORE UPDATE OR DELETE ON evaluation_definition_versions
        FOR EACH ROW EXECUTE FUNCTION prevent_published_evaluation_version_mutation()
    """)

    op.bulk_insert(
        sa.table(
            "evaluation_definitions",
            sa.column("id", sa.String), sa.column("owner_scope", sa.String),
            sa.column("owner_key", sa.String), sa.column("tenant_id", sa.String),
            sa.column("definition_key", sa.String), sa.column("name", sa.String),
            sa.column("active", sa.Boolean),
        ),
        [{
            "id": _DEFINITION_ID, "owner_scope": "system", "owner_key": _SYSTEM_KEY,
            "tenant_id": None, "definition_key": "voice_session_technical_health",
            "name": "Voice session technical health", "active": True,
        }],
    )
    op.bulk_insert(
        sa.table(
            "evaluation_definition_versions",
            sa.column("id", sa.String), sa.column("definition_id", sa.String),
            sa.column("owner_key", sa.String), sa.column("version", sa.Integer),
            sa.column("status", sa.String), sa.column("criteria_json", sa.JSON),
            sa.column("published_at", sa.DateTime(timezone=True)),
        ),
        [{
            "id": _VERSION_ID, "definition_id": _DEFINITION_ID, "owner_key": _SYSTEM_KEY,
            "version": 1, "status": "published", "criteria_json": _CRITERIA,
            "published_at": datetime(2026, 10, 7, tzinfo=timezone.utc),
        }],
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_published_evaluation_version_immutable ON evaluation_definition_versions")
    op.execute("DROP FUNCTION IF EXISTS prevent_published_evaluation_version_mutation()")
    op.drop_index("ix_evaluation_criterion_results_run", table_name="evaluation_criterion_results")
    op.drop_table("evaluation_criterion_results")
    op.drop_index("ix_evaluation_runs_subject", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_due", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
    op.drop_index("ix_evaluation_definition_versions_published", table_name="evaluation_definition_versions")
    op.drop_table("evaluation_definition_versions")
    op.drop_index("ix_evaluation_definitions_tenant", table_name="evaluation_definitions")
    op.drop_table("evaluation_definitions")
