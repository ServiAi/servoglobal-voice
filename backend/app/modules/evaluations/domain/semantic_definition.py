"""Reference content of system definition ``voice_session_semantic_quality`` v1.

The migration carries a frozen literal copy; a test asserts both stay identical. Changing any
rubric, threshold, prompt or criterion means publishing definition version N+1, never editing v1."""

from __future__ import annotations

from app.modules.evaluations.domain.semantic_judge import SCHEMA_VERSION
from app.modules.evaluations.domain.semantic_prompts import (
    resolve_prompt_latest_for_seed,
)

SEMANTIC_DEFINITION_KEY = "voice_session_semantic_quality"

# criterion -> (prompt_key, rubric_version, threshold, pass_verdicts, verdict -> (low, high))
_RUBRICS = {
    "goal_completion": (
        "goal-completion", "goal-completion-v1", 75, ["achieved"],
        {"achieved": [75, 100], "partially_achieved": [40, 74], "not_achieved": [0, 39]},
    ),
    "instruction_adherence": (
        "instruction-adherence", "instruction-adherence-v1", 75, ["adhered"],
        {"adhered": [75, 100], "partially_adhered": [40, 74], "violated": [0, 39]},
    ),
    "conversation_quality": (
        "conversation-quality", "conversation-quality-v1", 60, ["good", "acceptable"],
        {"good": [85, 100], "acceptable": [60, 84], "poor": [0, 59]},
    ),
}


def semantic_quality_criteria() -> list[dict]:
    criteria = []
    for key, (prompt_key, rubric_version, threshold, pass_verdicts, bands) in _RUBRICS.items():
        prompt = resolve_prompt_latest_for_seed(prompt_key, "1")
        criteria.append({
            "key": key, "evaluator_type": "llm", "weight": 1, "rubric_version": rubric_version,
            "prompt_key": prompt.key, "prompt_version": prompt.version, "prompt_hash": prompt.prompt_hash,
            "output_schema_version": SCHEMA_VERSION, "score_scale": "0-100", "threshold": threshold,
            "pass_verdicts": pass_verdicts, "verdict_bands": bands,
        })
    return criteria
