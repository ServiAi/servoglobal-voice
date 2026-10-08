"""Module 12B.2 semantic evaluation engine: outcome/verdict/provenance on criterion results
and the system definition voice_session_semantic_quality v1. Additive; existing rows are backfilled
from their boolean (passed=true -> pass, passed=false -> fail)."""

from datetime import datetime, timezone

import sqlalchemy as sa

from alembic import op

revision = "202610080001"
down_revision = "202610070001"
branch_labels = None
depends_on = None

_SYSTEM_KEY = "__system__"
_DEFINITION_ID = "00000000-0000-4000-8000-000000000014"
_VERSION_ID = "00000000-0000-4000-8000-000000000015"
# Frozen copy: published versions are immutable, so later changes ship as version N+1.
_CRITERIA = [
    {
        "key": "goal_completion",
        "evaluator_type": "llm",
        "weight": 1,
        "rubric_version": "goal-completion-v1",
        "prompt_key": "goal-completion",
        "prompt_version": "1",
        "prompt_hash": "843f70c00076d50a0e943f2c3e2618976e6b7c164c76ef7762ad86896328736f",
        "output_schema_version": "semantic-judge-result-v1",
        "score_scale": "0-100",
        "threshold": 75,
        "pass_verdicts": [
            "achieved"
        ],
        "verdict_bands": {
            "achieved": [
                75,
                100
            ],
            "partially_achieved": [
                40,
                74
            ],
            "not_achieved": [
                0,
                39
            ]
        }
    },
    {
        "key": "instruction_adherence",
        "evaluator_type": "llm",
        "weight": 1,
        "rubric_version": "instruction-adherence-v1",
        "prompt_key": "instruction-adherence",
        "prompt_version": "1",
        "prompt_hash": "a77ab5cd1558d315d0c474476a4912b1159161da0c32b53f514918487f3d81e9",
        "output_schema_version": "semantic-judge-result-v1",
        "score_scale": "0-100",
        "threshold": 75,
        "pass_verdicts": [
            "adhered"
        ],
        "verdict_bands": {
            "adhered": [
                75,
                100
            ],
            "partially_adhered": [
                40,
                74
            ],
            "violated": [
                0,
                39
            ]
        }
    },
    {
        "key": "conversation_quality",
        "evaluator_type": "llm",
        "weight": 1,
        "rubric_version": "conversation-quality-v1",
        "prompt_key": "conversation-quality",
        "prompt_version": "1",
        "prompt_hash": "cee715bf4ccbfa76a39e0af47e6d503bee58ae0154473e50705b9b50e0e5a905",
        "output_schema_version": "semantic-judge-result-v1",
        "score_scale": "0-100",
        "threshold": 60,
        "pass_verdicts": [
            "good",
            "acceptable"
        ],
        "verdict_bands": {
            "good": [
                85,
                100
            ],
            "acceptable": [
                60,
                84
            ],
            "poor": [
                0,
                59
            ]
        }
    }
]


def upgrade() -> None:
    op.add_column("evaluation_criterion_results", sa.Column("outcome", sa.String(24), nullable=True))
    op.add_column("evaluation_criterion_results", sa.Column("verdict", sa.String(40), nullable=True))
    op.add_column("evaluation_criterion_results", sa.Column("provenance_json", sa.JSON(), nullable=True))
    op.execute("UPDATE evaluation_criterion_results SET outcome = CASE WHEN passed THEN 'pass' ELSE 'fail' END")
    op.alter_column("evaluation_criterion_results", "outcome", nullable=False)
    op.alter_column("evaluation_criterion_results", "passed", existing_type=sa.Boolean(), nullable=True)
    op.create_check_constraint(
        "ck_evaluation_criterion_results_outcome", "evaluation_criterion_results",
        "outcome IN ('pass','fail','insufficient_evidence')",
    )
    op.create_check_constraint(
        "ck_evaluation_criterion_results_outcome_passed", "evaluation_criterion_results",
        "(outcome = 'pass' AND passed IS TRUE) OR (outcome = 'fail' AND passed IS FALSE) OR "
        "(outcome = 'insufficient_evidence' AND passed IS NULL AND score IS NULL)",
    )
    op.create_check_constraint(
        "ck_evaluation_criterion_results_llm_provenance", "evaluation_criterion_results",
        "evaluator_type <> 'llm' OR provenance_json IS NOT NULL",
    )

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
            "tenant_id": None, "definition_key": "voice_session_semantic_quality",
            "name": "Voice session semantic quality", "active": True,
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
            "published_at": datetime(2026, 10, 8, tzinfo=timezone.utc),
        }],
    )


def downgrade() -> None:
    # Published versions are immutable (trigger), so removal is explicit and ordered:
    # runs and results of the semantic definition first, then the version and definition.
    op.execute(
        "DELETE FROM evaluation_runs WHERE definition_version_id = '%s'" % _VERSION_ID
    )
    op.execute("ALTER TABLE evaluation_definition_versions DISABLE TRIGGER trg_published_evaluation_version_immutable")
    op.execute("DELETE FROM evaluation_definition_versions WHERE id = '%s'" % _VERSION_ID)
    op.execute("ALTER TABLE evaluation_definition_versions ENABLE TRIGGER trg_published_evaluation_version_immutable")
    op.execute("DELETE FROM evaluation_definitions WHERE id = '%s'" % _DEFINITION_ID)
    op.drop_constraint("ck_evaluation_criterion_results_llm_provenance", "evaluation_criterion_results", type_="check")
    op.drop_constraint("ck_evaluation_criterion_results_outcome_passed", "evaluation_criterion_results", type_="check")
    op.drop_constraint("ck_evaluation_criterion_results_outcome", "evaluation_criterion_results", type_="check")
    # Rows with passed IS NULL (insufficient_evidence) cannot satisfy NOT NULL; they are dropped.
    op.execute("DELETE FROM evaluation_criterion_results WHERE passed IS NULL")
    op.alter_column("evaluation_criterion_results", "passed", existing_type=sa.Boolean(), nullable=False)
    op.drop_column("evaluation_criterion_results", "provenance_json")
    op.drop_column("evaluation_criterion_results", "verdict")
    op.drop_column("evaluation_criterion_results", "outcome")
