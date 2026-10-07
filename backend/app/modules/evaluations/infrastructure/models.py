from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, String, UniqueConstraint, event, inspect
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import _utcnow, _uuid
from app.modules.evaluations.domain.errors import EvaluationDefinitionVersionImmutable

SYSTEM_OWNER_KEY = "__system__"


class EvaluationDefinition(Base):
    __tablename__ = "evaluation_definitions"
    __table_args__ = (
        CheckConstraint(
            "(owner_scope = 'system' AND tenant_id IS NULL AND owner_key = '__system__') OR "
            "(owner_scope = 'tenant' AND tenant_id IS NOT NULL AND owner_key = tenant_id)",
            name="ck_evaluation_definitions_owner",
        ),
        UniqueConstraint("id", "owner_key", name="uq_evaluation_definitions_id_owner"),
        UniqueConstraint("owner_key", "definition_key", name="uq_evaluation_definitions_owner_key"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        Index("ix_evaluation_definitions_tenant", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_scope: Mapped[str] = mapped_column(String(16), nullable=False)
    owner_key: Mapped[str] = mapped_column(String(36), nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    definition_key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True, server_default=sa.true())
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=_utcnow, server_default=sa.func.now()
    )


class EvaluationDefinitionVersion(Base):
    __tablename__ = "evaluation_definition_versions"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_evaluation_definition_versions_version"),
        CheckConstraint("status IN ('draft','published','superseded')", name="ck_evaluation_definition_versions_status"),
        ForeignKeyConstraint(
            ["definition_id", "owner_key"],
            ["evaluation_definitions.id", "evaluation_definitions.owner_key"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("definition_id", "version", name="uq_evaluation_definition_versions_number"),
        UniqueConstraint("id", "owner_key", name="uq_evaluation_definition_versions_id_owner"),
        Index("ix_evaluation_definition_versions_published", "owner_key", "status", "definition_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    definition_id: Mapped[str] = mapped_column(String(36), nullable=False)
    owner_key: Mapped[str] = mapped_column(String(36), nullable=False)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    criteria_json: Mapped[list] = mapped_column(sa.JSON, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=_utcnow, server_default=sa.func.now()
    )


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (
        CheckConstraint("owner_key = '__system__' OR owner_key = tenant_id", name="ck_evaluation_runs_definition_owner"),
        CheckConstraint("status IN ('queued','running','completed','failed','cancelled')", name="ck_evaluation_runs_status"),
        CheckConstraint("subject_type <> '' AND subject_id <> '' AND trigger_key <> ''", name="ck_evaluation_runs_identity"),
        CheckConstraint("attempt_count >= 0 AND claim_generation >= 0", name="ck_evaluation_runs_claim_counts"),
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 100", name="ck_evaluation_runs_score"),
        ForeignKeyConstraint(
            ["definition_version_id", "owner_key"],
            ["evaluation_definition_versions.id", "evaluation_definition_versions.owner_key"],
        ),
        UniqueConstraint(
            "tenant_id", "subject_type", "subject_id", "definition_version_id", "trigger_key",
            name="uq_evaluation_runs_identity",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_evaluation_runs_tenant_id"),
        Index("ix_evaluation_runs_due", "status", "next_attempt_at", "requested_at"),
        Index("ix_evaluation_runs_subject", "tenant_id", "subject_type", "subject_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    owner_key: Mapped[str] = mapped_column(String(36), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    definition_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    trigger_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued", server_default="queued")
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    conflict_detected_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    conflicting_evidence_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempt_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=_utcnow, server_default=sa.func.now()
    )
    claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    claim_generation: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0, server_default="0")
    lease_expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    passed: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    score: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=_utcnow, server_default=sa.func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class CriterionResult(Base):
    __tablename__ = "evaluation_criterion_results"
    __table_args__ = (
        CheckConstraint("evaluator_type IN ('deterministic','llm','human')", name="ck_evaluation_criterion_results_evaluator"),
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 100", name="ck_evaluation_criterion_results_score"),
        ForeignKeyConstraint(["tenant_id", "run_id"], ["evaluation_runs.tenant_id", "evaluation_runs.id"], ondelete="CASCADE"),
        UniqueConstraint("tenant_id", "run_id", "criterion_key", name="uq_evaluation_criterion_results_key"),
        Index("ix_evaluation_criterion_results_run", "tenant_id", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    criterion_key: Mapped[str] = mapped_column(String(100), nullable=False)
    evaluator_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="deterministic", server_default="deterministic"
    )
    implementation_version: Mapped[str] = mapped_column(String(40), nullable=False)
    passed: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    score: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    evidence_ref_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=_utcnow, server_default=sa.func.now()
    )


@event.listens_for(EvaluationDefinitionVersion, "before_update")
@event.listens_for(EvaluationDefinitionVersion, "before_delete")
def _published_definition_version_is_immutable(_mapper, _connection, target: EvaluationDefinitionVersion) -> None:
    if target.status == "published" or "published" in inspect(target).attrs.status.history.deleted:
        raise EvaluationDefinitionVersionImmutable("published_evaluation_definition_version_is_immutable")
