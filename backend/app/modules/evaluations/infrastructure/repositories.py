from __future__ import annotations

import copy
import hashlib
import json
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.evaluations.application.contracts import (
    CriterionResultView,
    EvaluationResultView,
    EvaluationRunView,
)
from app.modules.evaluations.application.semantic_evaluator import (
    IMPLEMENTATION_VERSION as _SEMANTIC_IMPLEMENTATION_VERSION,
)
from app.modules.evaluations.application.semantic_evaluator import (
    SemanticEvaluator,
)
from app.modules.evaluations.domain.engine import evaluate
from app.modules.evaluations.domain.errors import (
    EvaluationDefinitionNotFound,
    EvaluationError,
    EvaluationInvalidEvidence,
    SemanticJudgeConfigurationError,
)
from app.modules.evaluations.domain.semantic_evidence import (
    SemanticEvaluationEvidenceV1,
    evidence_from_payload,
    evidence_payload,
)
from app.modules.evaluations.domain.semantic_judge import LlmJudgePort
from app.modules.evaluations.domain.technical_health import (
    ToolOutcomeEvidence,
    VoiceSessionEvidence,
)
from app.modules.evaluations.infrastructure.models import (
    SYSTEM_OWNER_KEY,
    CriterionResult,
    EvaluationDefinition,
    EvaluationDefinitionVersion,
    EvaluationRun,
)

_MAX_ATTEMPTS = 5
_IMPLEMENTATION_VERSION = "deterministic-v1"
_TECHNICAL_DEFINITION = "voice_session_technical_health"
_SEMANTIC_DEFINITION = "voice_session_semantic_quality"


@dataclass(frozen=True)
class _Plan:
    """Everything the evaluator needs, copied out of the ORM so it can run with no transaction."""

    tenant_id: str
    run_id: str
    subject_type: str
    subject_id: str
    evidence_hash: str
    evidence_json: dict
    criteria: list | None


@dataclass(frozen=True)
class _Outcome:
    passed: bool | None
    score: int | None
    reason: str
    rows: list[dict]


class EvaluationRepository:
    """Persistence adapter for evaluation request, query, and worker operations."""

    def __init__(self, db: Session, semantic_judge: LlmJudgePort | None = None) -> None:
        self.db = db
        self.semantic_judge = semantic_judge

    def request_voice_session(self, evidence: VoiceSessionEvidence, *, trigger_key: str) -> EvaluationRunView:
        snapshot = asdict(evidence)
        snapshot["ended_at"] = evidence.ended_at.isoformat()
        evidence_hash = hashlib.sha256(
            json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return self._request(
            _TECHNICAL_DEFINITION, tenant_id=evidence.tenant_id, session_id=evidence.session_id,
            agent_version_id=evidence.agent_version_id, source="voice_terminal", trigger_key=trigger_key,
            evidence_json=snapshot, evidence_hash=evidence_hash,
        )

    def request_semantic_session(
        self, evidence: SemanticEvaluationEvidenceV1, *, trigger_key: str
    ) -> EvaluationRunView:
        # Stores the redacted canonical payload (not the raw transcript) plus its hash.
        payload = evidence_payload(evidence)
        evidence_from_payload(payload, expected_hash=evidence.evidence_hash)
        return self._request(
            _SEMANTIC_DEFINITION, tenant_id=evidence.tenant_id, session_id=evidence.session_id,
            agent_version_id=evidence.agent_version_id, source="semantic_evidence", trigger_key=trigger_key,
            evidence_json=payload, evidence_hash=evidence.evidence_hash,
        )

    def _request(
        self, definition_key: str, *, tenant_id: str, session_id: str, agent_version_id: str | None,
        source: str, trigger_key: str, evidence_json: dict, evidence_hash: str,
    ) -> EvaluationRunView:
        if not trigger_key or len(trigger_key) > 255:
            raise ValueError("evaluation_trigger_key_invalid")
        definition = self.db.scalar(select(EvaluationDefinition).where(
            EvaluationDefinition.owner_key == SYSTEM_OWNER_KEY,
            EvaluationDefinition.definition_key == definition_key,
            EvaluationDefinition.active.is_(True),
        ))
        if definition is None:
            raise EvaluationDefinitionNotFound(definition_key)
        version = self.db.scalar(select(EvaluationDefinitionVersion).where(
            EvaluationDefinitionVersion.definition_id == definition.id,
            EvaluationDefinitionVersion.owner_key == SYSTEM_OWNER_KEY,
            EvaluationDefinitionVersion.status == "published",
        ).order_by(EvaluationDefinitionVersion.version.desc()).limit(1))
        if version is None:
            raise EvaluationDefinitionNotFound(definition_key + "_version")

        identity = (
            EvaluationRun.tenant_id == tenant_id,
            EvaluationRun.subject_type == "voice_session",
            EvaluationRun.subject_id == session_id,
            EvaluationRun.definition_version_id == version.id,
            EvaluationRun.trigger_key == trigger_key,
        )
        existing = self.db.scalar(select(EvaluationRun).where(*identity).with_for_update())
        if existing is not None:
            return self._reuse_or_record_conflict(existing, evidence_hash)
        run = EvaluationRun(
            tenant_id=tenant_id,
            owner_key=SYSTEM_OWNER_KEY,
            subject_type="voice_session",
            subject_id=session_id,
            agent_version_id=agent_version_id,
            definition_version_id=version.id,
            source=source,
            trigger_key=trigger_key,
            status="queued",
            evidence_hash=evidence_hash,
            evidence_json=evidence_json,
        )
        try:
            # Keep enqueue in the caller's transaction while containing unique races.
            with self.db.begin_nested():
                self.db.add(run)
                self.db.flush()
        except IntegrityError:
            existing = self.db.scalar(select(EvaluationRun).where(*identity).with_for_update())
            if existing is None:
                raise
            return self._reuse_or_record_conflict(existing, evidence_hash)
        return self._view(run)

    def _reuse_or_record_conflict(self, run: EvaluationRun, evidence_hash: str) -> EvaluationRunView:
        if run.evidence_hash != evidence_hash:
            run.conflict_detected_at = datetime.now(timezone.utc)
            run.conflicting_evidence_hash = evidence_hash
            self.db.flush()
        return self._view(run)

    @staticmethod
    def _view(run: EvaluationRun) -> EvaluationRunView:
        return EvaluationRunView(
            id=run.id, tenant_id=run.tenant_id, subject_type=run.subject_type,
            subject_id=run.subject_id, agent_version_id=run.agent_version_id,
            definition_version_id=run.definition_version_id, status=run.status,
            evidence_hash=run.evidence_hash,
            evidence_conflict=run.conflicting_evidence_hash is not None,
            passed=run.passed, score=run.score, reason=run.reason,
            requested_at=run.requested_at, evaluated_at=run.evaluated_at,
        )

    def get(self, tenant_id: str, run_id: str) -> EvaluationResultView | None:
        run = self.db.scalar(select(EvaluationRun).where(
            EvaluationRun.tenant_id == tenant_id, EvaluationRun.id == run_id
        ))
        if run is None:
            return None
        criteria = self.db.scalars(select(CriterionResult).where(
            CriterionResult.tenant_id == tenant_id, CriterionResult.run_id == run.id
        ).order_by(CriterionResult.criterion_key)).all()
        return EvaluationResultView(
            run=self._view(run),
            criteria=tuple(CriterionResultView(
                criterion_key=row.criterion_key, evaluator_type=row.evaluator_type,
                implementation_version=row.implementation_version, passed=row.passed,
                score=row.score, reason=row.reason, evidence_ref=row.evidence_ref_json,
                outcome=row.outcome, verdict=row.verdict, provenance=row.provenance_json,
            ) for row in criteria),
        )

    def claim_batch(self, *, now: datetime, lease_seconds: int, batch_size: int) -> list[dict]:
        due = or_(
            (EvaluationRun.status == "queued") & (EvaluationRun.next_attempt_at <= now),
            (EvaluationRun.status == "running") & (EvaluationRun.lease_expires_at <= now),
        )
        rows = self.db.scalars(select(EvaluationRun).where(due)
            .order_by(EvaluationRun.next_attempt_at, EvaluationRun.requested_at, EvaluationRun.id)
            .limit(batch_size).with_for_update(skip_locked=True)).all()
        claims = []
        for run in rows:
            if run.attempt_count >= _MAX_ATTEMPTS:
                run.status = "failed"
                run.last_error_code = run.last_error_code or "evaluation_attempts_exhausted"
                run.claim_token = run.lease_expires_at = None
                continue
            run.status = "running"
            run.attempt_count += 1
            run.claim_generation += 1
            run.claim_token = secrets.token_urlsafe(24)
            run.lease_expires_at = now + timedelta(seconds=lease_seconds)
            run.started_at = now
            claims.append({"run_id": run.id, "tenant_id": run.tenant_id,
                           "claim_token": run.claim_token, "claim_generation": run.claim_generation})
        self.db.commit()
        return claims

    def execute(self, claim: dict, *, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        plan = self._load_plan(claim)  # TX2: read, copy to plain values, end the transaction
        if plan is None:
            return False
        try:
            outcome = self._compute(plan)  # no database access: a slow/network judge holds no transaction
        except Exception as exc:
            return self._record_failure(claim, now=now, code=_safe_error_code(exc), retryable=_is_retryable(exc))
        return self._persist(claim, outcome, now)  # TX3: re-verify claim/generation/lease, then write

    def _load_plan(self, claim: dict) -> _Plan | None:
        run = self.db.scalar(select(EvaluationRun).where(
            EvaluationRun.id == claim["run_id"], EvaluationRun.tenant_id == claim["tenant_id"],
            EvaluationRun.status == "running", EvaluationRun.claim_token == claim["claim_token"],
            EvaluationRun.claim_generation == claim["claim_generation"],
        ))
        if run is None:
            return None
        version = self.db.scalar(select(EvaluationDefinitionVersion).where(
            EvaluationDefinitionVersion.id == run.definition_version_id,
            EvaluationDefinitionVersion.owner_key == run.owner_key,
        ))
        plan = _Plan(
            tenant_id=run.tenant_id, run_id=run.id, subject_type=run.subject_type, subject_id=run.subject_id,
            evidence_hash=run.evidence_hash, evidence_json=copy.deepcopy(run.evidence_json),
            criteria=copy.deepcopy(version.criteria_json) if version is not None else None,
        )
        self.db.commit()
        return plan

    def _compute(self, plan: _Plan) -> _Outcome:
        if plan.criteria is None:
            raise ValueError("evaluation_definition_version_not_found")
        if plan.criteria and all(c.get("evaluator_type") == "llm" for c in plan.criteria):
            return self._compute_semantic(plan)
        evidence = _evidence_from_snapshot(plan.evidence_json)
        if evidence.tenant_id != plan.tenant_id or evidence.session_id != plan.subject_id:
            raise ValueError("evaluation_evidence_subject_mismatch")
        result = evaluate(plan.criteria, evidence)
        return _Outcome(result.passed, result.score, result.reason, [
            {"criterion_key": c.key, "evaluator_type": "deterministic",
             "implementation_version": _IMPLEMENTATION_VERSION,
             "outcome": "pass" if c.passed else "fail", "verdict": None, "passed": c.passed,
             "score": 100 if c.passed else 0, "reason": c.reason, "provenance_json": None,
             "evidence_ref": {"fields": c.evidence_field}}
            for c in result.criteria
        ])

    def _compute_semantic(self, plan: _Plan) -> _Outcome:
        evidence = evidence_from_payload(plan.evidence_json, expected_hash=plan.evidence_hash)
        if evidence.tenant_id != plan.tenant_id or evidence.session_id != plan.subject_id:
            raise EvaluationInvalidEvidence("evaluation_evidence_subject_mismatch")
        if self.semantic_judge is None:
            raise SemanticJudgeConfigurationError("semantic_judge_not_configured")
        result = SemanticEvaluator(self.semantic_judge).evaluate(plan.criteria, evidence)
        return _Outcome(result.passed, result.score, result.reason, [
            {"criterion_key": c.key, "evaluator_type": "llm",
             "implementation_version": _SEMANTIC_IMPLEMENTATION_VERSION,
             "outcome": c.outcome, "verdict": c.verdict, "passed": c.passed, "score": c.score,
             "reason": c.reason, "provenance_json": c.provenance,
             "evidence_ref": {"turn_ids": list(c.evidence_turn_ids)}}
            for c in result.criteria
        ])

    def _persist(self, claim: dict, outcome: _Outcome, now: datetime) -> bool:
        locked = self.db.scalar(select(EvaluationRun).where(
            EvaluationRun.id == claim["run_id"], EvaluationRun.tenant_id == claim["tenant_id"],
            EvaluationRun.status == "running", EvaluationRun.claim_token == claim["claim_token"],
            EvaluationRun.claim_generation == claim["claim_generation"], EvaluationRun.lease_expires_at > now,
        ).with_for_update())
        if locked is None:
            self.db.rollback()
            return False
        for row in outcome.rows:
            ref = {"subject_type": locked.subject_type, "subject_id": locked.subject_id,
                   **row["evidence_ref"], "evidence_hash": locked.evidence_hash}
            self.db.add(CriterionResult(
                tenant_id=locked.tenant_id, run_id=locked.id, evidence_ref_json=ref,
                **{k: v for k, v in row.items() if k != "evidence_ref"},
            ))
        locked.status, locked.passed, locked.score, locked.reason = (
            "completed", outcome.passed, outcome.score, outcome.reason
        )
        locked.evaluated_at = now
        locked.claim_token = locked.lease_expires_at = None
        self.db.commit()
        return True

    def _record_failure(self, claim: dict, *, now: datetime, code: str, retryable: bool) -> bool:
        run = self.db.scalar(select(EvaluationRun).where(
            EvaluationRun.id == claim["run_id"], EvaluationRun.tenant_id == claim["tenant_id"],
            EvaluationRun.status == "running", EvaluationRun.claim_token == claim["claim_token"],
            EvaluationRun.claim_generation == claim["claim_generation"], EvaluationRun.lease_expires_at > now,
        ).with_for_update())
        if run is None:
            self.db.rollback()
            return False
        run.last_error_code = code
        run.claim_token = run.lease_expires_at = None
        if not retryable or run.attempt_count >= _MAX_ATTEMPTS:
            run.status = "failed"
        else:
            run.status = "queued"
            run.next_attempt_at = now + timedelta(seconds=min(2 ** run.attempt_count, 300))
        self.db.commit()
        return True


def _evidence_from_snapshot(snapshot: dict) -> VoiceSessionEvidence:
    evidence = dict(snapshot)
    evidence["ended_at"] = datetime.fromisoformat(evidence["ended_at"])
    evidence["tool_outcomes"] = tuple(ToolOutcomeEvidence(**row) for row in evidence.get("tool_outcomes", []))
    return VoiceSessionEvidence(**evidence)


def _safe_error_code(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, str) and 0 < len(code) <= 80 and code.replace("_", "").isalnum():
        return code
    return "evaluation_execution_failed"


def _is_retryable(exc: Exception) -> bool:
    declared = getattr(exc, "retryable", None)
    if isinstance(declared, bool):
        return declared
    return not isinstance(exc, (ValueError, EvaluationError))
