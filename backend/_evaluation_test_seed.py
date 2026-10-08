from __future__ import annotations

from datetime import datetime, timezone

from app.modules.evaluations.domain.semantic_definition import (
    SEMANTIC_DEFINITION_KEY,
    semantic_quality_criteria,
)
from app.modules.evaluations.infrastructure.models import (
    SYSTEM_OWNER_KEY,
    EvaluationDefinition,
    EvaluationDefinitionVersion,
)


def seed_voice_technical_health(db) -> None:
    """Replica la siembra de la migración 202610070001; create_all no la ejecuta."""
    definition = EvaluationDefinition(
        owner_scope="system", owner_key=SYSTEM_OWNER_KEY, tenant_id=None,
        definition_key="voice_session_technical_health", name="Voice session technical health",
        active=True,
    )
    db.add(definition)
    db.flush()
    db.add(EvaluationDefinitionVersion(
        definition_id=definition.id, owner_key=SYSTEM_OWNER_KEY, version=1,
        status="published", published_at=datetime.now(timezone.utc),
        criteria_json=[
            {"key": key, "evaluator_type": "deterministic", "weight": 1}
            for key in ("session_terminal", "runtime_health", "tool_execution_health")
        ],
    ))
    db.commit()


def seed_voice_semantic_quality(db) -> None:
    """Replica la siembra semántica de la migración 202610080001."""
    definition = EvaluationDefinition(
        owner_scope="system", owner_key=SYSTEM_OWNER_KEY, tenant_id=None,
        definition_key=SEMANTIC_DEFINITION_KEY, name="Voice session semantic quality", active=True,
    )
    db.add(definition)
    db.flush()
    db.add(EvaluationDefinitionVersion(
        definition_id=definition.id, owner_key=SYSTEM_OWNER_KEY, version=1,
        status="published", published_at=datetime.now(timezone.utc),
        criteria_json=semantic_quality_criteria(),
    ))
    db.commit()
