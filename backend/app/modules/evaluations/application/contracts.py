from dataclasses import dataclass
from datetime import datetime

from app.modules.evaluations.domain.technical_health import VoiceSessionEvidence


@dataclass(frozen=True)
class EvaluationRunView:
    id: str
    tenant_id: str
    subject_type: str
    subject_id: str
    agent_version_id: str | None
    definition_version_id: str
    status: str
    evidence_hash: str
    evidence_conflict: bool
    passed: bool | None
    score: int | None
    reason: str | None
    requested_at: datetime
    evaluated_at: datetime | None


@dataclass(frozen=True)
class CriterionResultView:
    criterion_key: str
    evaluator_type: str
    implementation_version: str
    passed: bool | None
    score: int | None
    reason: str
    evidence_ref: dict
    outcome: str = "pass"
    verdict: str | None = None
    provenance: dict | None = None


@dataclass(frozen=True)
class EvaluationResultView:
    run: EvaluationRunView
    criteria: tuple[CriterionResultView, ...]


__all__ = [
    "CriterionResultView",
    "EvaluationResultView",
    "EvaluationRunView",
    "VoiceSessionEvidence",
]
