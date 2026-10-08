"""Semantic evaluation use case. Pure: takes frozen DTOs and a judge port, returns frozen results.

It never touches a database session, so a caller can run it with no transaction open."""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.modules.evaluations.domain.errors import (
    EvaluationInvalidDefinition,
    SemanticEvidenceMissing,
    SemanticInputLimitExceeded,
    SemanticRubricInvalid,
)
from app.modules.evaluations.domain.semantic_evidence import (
    SemanticEvaluationEvidenceV1,
)
from app.modules.evaluations.domain.semantic_judge import (
    CRITERION_VERDICTS,
    OUTCOME_FAIL,
    OUTCOME_INSUFFICIENT,
    SCHEMA_VERSION,
    InputLimits,
    LlmJudgePort,
    SemanticJudgeRequest,
    normalize_response,
    parse_rubric,
)
from app.modules.evaluations.domain.semantic_prompts import resolve_prompt

IMPLEMENTATION_VERSION = "semantic-evaluator-v1"


@dataclass(frozen=True)
class CriterionEvaluation:
    key: str
    verdict: str
    outcome: str
    passed: bool | None
    score: int | None
    reason: str
    evidence_turn_ids: tuple[str, ...]
    provenance: dict


@dataclass(frozen=True)
class SemanticRunResult:
    passed: bool | None
    score: int | None
    reason: str
    criteria: tuple[CriterionEvaluation, ...]


def render_evidence_block(evidence: SemanticEvaluationEvidenceV1) -> str:
    """How an adapter must present the conversation: one JSON data block, never prompt text.
    JSON escaping keeps transcript content inert inside a quoted string."""
    return json.dumps(
        {
            "agent": {
                "role": evidence.agent_snapshot.role, "objective": evidence.agent_snapshot.objective,
                "system_prompt": evidence.agent_snapshot.system_prompt,
                "greeting": evidence.agent_snapshot.greeting, "closing": evidence.agent_snapshot.closing,
            },
            "turns": [
                {"event_id": t.event_id, "speaker": t.speaker, "text": t.text} for t in evidence.turns
            ],
        },
        ensure_ascii=False,
    )


class SemanticEvaluator:
    def __init__(self, judge: LlmJudgePort, *, limits: InputLimits | None = None) -> None:
        self.judge = judge
        self.limits = limits or InputLimits()

    def evaluate(self, criteria: list[dict], evidence: SemanticEvaluationEvidenceV1) -> SemanticRunResult:
        """Atomic: every criterion succeeds or the whole call raises (no partial results)."""
        keys = [c.get("key") for c in criteria if isinstance(c, dict)]
        if sorted(keys) != sorted(CRITERION_VERDICTS) or len(criteria) != len(keys):
            raise EvaluationInvalidDefinition("evaluation_semantic_criteria_invalid")
        if not evidence.turns:
            raise SemanticEvidenceMissing()
        if len(evidence.turns) > self.limits.max_turns or sum(len(t.text) for t in evidence.turns) \
                > self.limits.max_transcript_chars:
            raise SemanticInputLimitExceeded()
        known_turn_ids = frozenset(turn.event_id for turn in evidence.turns)

        results = []
        for config in sorted(criteria, key=lambda c: c["key"]):
            rubric = parse_rubric(config)
            prompt = resolve_prompt(
                _text(config, "prompt_key"), _text(config, "prompt_version"), _text(config, "prompt_hash")
            )
            request = SemanticJudgeRequest(
                criterion_key=rubric.criterion_key, rubric=rubric, prompt=prompt, evidence=evidence,
                output_schema_version=SCHEMA_VERSION, limits=self.limits,
                language=evidence.agent_snapshot.language,
            )
            response = self.judge.evaluate(request)
            verdict = normalize_response(rubric, response, known_turn_ids)
            meta = response.metadata
            provenance = {
                "provider": meta.provider, "requested_model": meta.requested_model,
                "resolved_model": meta.resolved_model, "model_revision": meta.model_revision,
                "prompt_key": prompt.key, "prompt_version": prompt.version, "prompt_hash": prompt.prompt_hash,
                "rubric_version": rubric.rubric_version, "schema_version": SCHEMA_VERSION,
                "implementation_version": IMPLEMENTATION_VERSION, "latency_ms": meta.latency_ms,
                "input_tokens": meta.input_tokens, "output_tokens": meta.output_tokens,
            }
            results.append(CriterionEvaluation(
                key=rubric.criterion_key, verdict=verdict.verdict, outcome=verdict.outcome,
                passed=verdict.passed, score=verdict.score, reason=verdict.reason,
                evidence_turn_ids=verdict.evidence_turn_ids, provenance=provenance,
            ))
        return _aggregate(tuple(results))


def _text(config: dict, key: str) -> str:
    value = config.get(key)
    if not isinstance(value, str) or not value:
        raise SemanticRubricInvalid()
    return value


def _aggregate(results: tuple[CriterionEvaluation, ...]) -> SemanticRunResult:
    scored = [r.score for r in results if r.score is not None]
    score = round(sum(scored) / len(scored)) if scored else None
    if any(r.outcome == OUTCOME_FAIL for r in results):
        passed, reason = False, "One or more semantic criteria did not pass."
    elif any(r.outcome == OUTCOME_INSUFFICIENT for r in results):
        passed, reason = None, "Evidence was insufficient for one or more semantic criteria."
    else:
        passed, reason = True, "All semantic criteria passed."
    return SemanticRunResult(passed=passed, score=score, reason=reason, criteria=results)


__all__ = ["CriterionEvaluation", "SemanticEvaluator", "SemanticRunResult", "render_evidence_block"]
