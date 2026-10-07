from dataclasses import dataclass

from app.modules.evaluations.domain.errors import EvaluationInvalidDefinition
from app.modules.evaluations.domain.technical_health import VoiceSessionEvidence


@dataclass(frozen=True)
class EvaluatedCriterion:
    key: str
    passed: bool
    reason: str
    evidence_field: str
    weight: int


@dataclass(frozen=True)
class EvaluatedResult:
    passed: bool
    score: int
    reason: str
    criteria: tuple[EvaluatedCriterion, ...]


def evaluate(criteria: list[dict], evidence: VoiceSessionEvidence) -> EvaluatedResult:
    outcomes = {
        "session_terminal": (
            evidence.status in {"ended", "failed", "cancelled"},
            f"Session status is {evidence.status}.",
            "status",
        ),
        "runtime_health": (
            evidence.status == "ended" and evidence.error_code is None,
            "No runtime failure was recorded."
            if evidence.status == "ended" and evidence.error_code is None
            else f"Runtime did not end cleanly: {evidence.error_code or evidence.status}.",
            "status,error_code",
        ),
        "tool_execution_health": (
            evidence.tool_failure_count == 0,
            "No tool execution failures were recorded."
            if evidence.tool_failure_count == 0
            else f"Tool failures recorded: {evidence.tool_failure_count}.",
            "tool_outcomes",
        ),
    }
    results: list[EvaluatedCriterion] = []
    for criterion in criteria:
        key = criterion.get("key")
        if criterion.get("evaluator_type") != "deterministic" or key not in outcomes:
            raise EvaluationInvalidDefinition("evaluation_criterion_unsupported")
        passed, reason, evidence_field = outcomes[key]
        weight = criterion.get("weight", 1)
        if not isinstance(weight, int) or weight <= 0:
            raise EvaluationInvalidDefinition("evaluation_criterion_weight_invalid")
        results.append(EvaluatedCriterion(key, passed, reason, evidence_field, weight))
    if not results:
        raise EvaluationInvalidDefinition("evaluation_definition_has_no_criteria")
    total_weight = sum(result.weight for result in results)
    passed_weight = sum(result.weight for result in results if result.passed)
    passed = passed_weight == total_weight
    return EvaluatedResult(
        passed=passed,
        score=round(passed_weight * 100 / total_weight),
        reason="All technical health criteria passed."
        if passed
        else "One or more technical health criteria failed.",
        criteria=tuple(results),
    )
