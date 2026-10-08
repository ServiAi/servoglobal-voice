"""Provider-neutral semantic judge contracts: rubric, request/response, port and the pure
validation that turns a judge response into a normalized criterion verdict.

Nothing here may carry ORM objects, sessions, credentials or HTTP objects."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from app.modules.evaluations.domain.errors import (
    SemanticJudgeEvidenceMismatch,
    SemanticJudgeInvalidOutput,
    SemanticRubricInvalid,
)
from app.modules.evaluations.domain.semantic_evidence import (
    SemanticEvaluationEvidenceV1,
)
from app.modules.evaluations.domain.semantic_prompts import PromptAsset

SCHEMA_VERSION = "semantic-judge-result-v1"
INSUFFICIENT = "insufficient_evidence"
OUTCOME_PASS, OUTCOME_FAIL, OUTCOME_INSUFFICIENT = "pass", "fail", "insufficient_evidence"
MAX_REASON_CHARS = 500
MAX_EVIDENCE_IDS = 10

# Closed, per-criterion verdict taxonomy (insufficient_evidence is shared and added separately).
CRITERION_VERDICTS: dict[str, tuple[str, ...]] = {
    "goal_completion": ("achieved", "partially_achieved", "not_achieved"),
    "instruction_adherence": ("adhered", "partially_adhered", "violated"),
    "conversation_quality": ("good", "acceptable", "poor"),
}

_SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$")


@dataclass(frozen=True)
class RubricSpec:
    criterion_key: str
    rubric_version: str
    threshold: int
    score_scale: str
    verdict_bands: tuple[tuple[str, int, int], ...]
    pass_verdicts: tuple[str, ...]

    def band(self, verdict: str) -> tuple[int, int]:
        for name, low, high in self.verdict_bands:
            if name == verdict:
                return low, high
        raise KeyError(verdict)


@dataclass(frozen=True)
class InputLimits:
    max_turns: int = 400
    max_transcript_chars: int = 60_000


@dataclass(frozen=True)
class SemanticJudgeRequest:
    criterion_key: str
    rubric: RubricSpec
    prompt: PromptAsset
    evidence: SemanticEvaluationEvidenceV1
    output_schema_version: str
    limits: InputLimits
    language: str


@dataclass(frozen=True)
class JudgeMetadata:
    """Neutral facts about the call. Whitelisted fields only: no headers, bodies or credentials."""

    provider: str
    requested_model: str
    resolved_model: str | None = None
    model_revision: str | None = None
    latency_ms: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class SemanticJudgeResponse:
    criterion_key: str
    verdict: str
    score: int | None
    reason: str
    evidence_turn_ids: tuple[str, ...]
    metadata: JudgeMetadata


class LlmJudgePort(Protocol):
    """May raise the typed SemanticJudge* errors (timeout, rate_limited, unavailable,
    invalid_output, configuration_error). Must not mutate the request."""

    def evaluate(self, request: SemanticJudgeRequest) -> SemanticJudgeResponse: ...


@dataclass(frozen=True)
class NormalizedVerdict:
    verdict: str
    outcome: str
    passed: bool | None
    score: int | None
    reason: str
    evidence_turn_ids: tuple[str, ...]


def parse_rubric(config: dict) -> RubricSpec:
    """Validate one criteria_json entry; a malformed pinned rubric is never repaired."""
    try:
        key = config["key"]
        if key not in CRITERION_VERDICTS:
            raise SemanticRubricInvalid()
        if config["evaluator_type"] != "llm" or config["score_scale"] != "0-100":
            raise SemanticRubricInvalid()
        if config["output_schema_version"] != SCHEMA_VERSION:
            raise SemanticRubricInvalid()
        threshold = config["threshold"]
        if isinstance(threshold, bool) or not isinstance(threshold, int) or not 0 <= threshold <= 100:
            raise SemanticRubricInvalid()
        verdicts = CRITERION_VERDICTS[key]
        bands = config["verdict_bands"]
        if not isinstance(bands, dict) or set(bands) != set(verdicts):
            raise SemanticRubricInvalid()
        parsed = []
        for verdict in verdicts:
            low, high = bands[verdict]
            if not all(isinstance(n, int) and not isinstance(n, bool) for n in (low, high)) \
                    or not 0 <= low <= high <= 100:
                raise SemanticRubricInvalid()
            parsed.append((verdict, low, high))
        pass_verdicts = tuple(config["pass_verdicts"])
        if not pass_verdicts or not set(pass_verdicts) <= set(verdicts):
            raise SemanticRubricInvalid()
        for verdict, low, high in parsed:
            # A verdict's band must sit entirely on its own side of the threshold.
            if (verdict in pass_verdicts and low < threshold) or (verdict not in pass_verdicts and high >= threshold):
                raise SemanticRubricInvalid()
        rubric_version = config["rubric_version"]
        if not isinstance(rubric_version, str) or not _SAFE_LABEL.match(rubric_version):
            raise SemanticRubricInvalid()
    except SemanticRubricInvalid:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise SemanticRubricInvalid() from exc
    return RubricSpec(key, rubric_version, threshold, "0-100", tuple(parsed), pass_verdicts)


def normalize_response(
    rubric: RubricSpec, response: object, known_turn_ids: frozenset[str]
) -> NormalizedVerdict:
    """Pure verdict/score/threshold/outcome consistency. Anything inconsistent is rejected."""
    if not isinstance(response, SemanticJudgeResponse) or response.criterion_key != rubric.criterion_key:
        raise SemanticJudgeInvalidOutput()
    verdict = response.verdict
    if verdict != INSUFFICIENT and verdict not in CRITERION_VERDICTS[rubric.criterion_key]:
        raise SemanticJudgeInvalidOutput()
    reason = response.reason
    if not isinstance(reason, str) or not reason.strip() or len(reason) > MAX_REASON_CHARS:
        raise SemanticJudgeInvalidOutput()
    ids = response.evidence_turn_ids
    if not isinstance(ids, (tuple, list)) or len(ids) > MAX_EVIDENCE_IDS \
            or not all(isinstance(i, str) and i for i in ids) or len(set(ids)) != len(ids):
        raise SemanticJudgeInvalidOutput()
    if any(i not in known_turn_ids for i in ids):
        raise SemanticJudgeEvidenceMismatch()
    _validate_metadata(response.metadata)

    score = response.score
    if verdict == INSUFFICIENT:
        if score is not None:
            raise SemanticJudgeInvalidOutput()
        return NormalizedVerdict(verdict, OUTCOME_INSUFFICIENT, None, None, reason.strip(), tuple(ids))
    if isinstance(score, bool) or not isinstance(score, int):
        raise SemanticJudgeInvalidOutput()
    low, high = rubric.band(verdict)
    if not low <= score <= high:
        raise SemanticJudgeInvalidOutput()
    passed = verdict in rubric.pass_verdicts and score >= rubric.threshold
    if (verdict in rubric.pass_verdicts) != passed:
        raise SemanticJudgeInvalidOutput()
    return NormalizedVerdict(
        verdict, OUTCOME_PASS if passed else OUTCOME_FAIL, passed, score, reason.strip(), tuple(ids)
    )


def _validate_metadata(metadata: object) -> None:
    if not isinstance(metadata, JudgeMetadata):
        raise SemanticJudgeInvalidOutput()
    for value in (metadata.provider, metadata.requested_model):
        if not isinstance(value, str) or not _SAFE_LABEL.match(value):
            raise SemanticJudgeInvalidOutput()
    for value in (metadata.resolved_model, metadata.model_revision):
        if value is not None and (not isinstance(value, str) or not _SAFE_LABEL.match(value)):
            raise SemanticJudgeInvalidOutput()
    for value in (metadata.latency_ms, metadata.input_tokens, metadata.output_tokens):
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            raise SemanticJudgeInvalidOutput()
