"""Import-light public API. SQLAlchemy is loaded only when a method is called."""

from typing import TYPE_CHECKING

from app.modules.evaluations.application.contracts import (
    CriterionResultView,
    EvaluationResultView,
    EvaluationRunView,
)
from app.modules.evaluations.domain.technical_health import (
    ToolOutcomeEvidence,
    VoiceSessionEvidence,
)

if TYPE_CHECKING:
    from app.modules.evaluations.domain.semantic_evidence import (
        SemanticEvaluationEvidenceV1,
    )


def _repository(db: object) -> object:
    from app.modules.evaluations.infrastructure.repositories import EvaluationRepository

    return EvaluationRepository(db)


class EvaluationRunner:
    def __init__(self, db: object) -> None:
        self.db = db

    def request_voice_session(self, evidence: VoiceSessionEvidence, *, trigger_key: str) -> EvaluationRunView:
        from app.modules.evaluations.application.request_evaluation import (
            EvaluationRequestService,
        )

        return EvaluationRequestService(_repository(self.db)).request_voice_session(evidence, trigger_key=trigger_key)

    def request_semantic_session(
        self, evidence: "SemanticEvaluationEvidenceV1", *, trigger_key: str
    ) -> EvaluationRunView:
        """Explicit (not automatic) semantic run; idempotent on evidence_hash like the technical run."""
        from app.modules.evaluations.application.request_evaluation import (
            EvaluationRequestService,
        )

        return EvaluationRequestService(_repository(self.db)).request_semantic_session(
            evidence, trigger_key=trigger_key
        )


class EvaluationQueries:
    def __init__(self, db: object) -> None:
        self.db = db

    def get(self, tenant_id: str, run_id: str) -> EvaluationResultView | None:
        from app.modules.evaluations.application.queries import (
            EvaluationQueries as Queries,
        )

        return Queries(_repository(self.db)).get(tenant_id, run_id)


class EvaluationFacade:
    def __init__(self, db: object) -> None:
        self.db = db

    def runner(self) -> EvaluationRunner:
        return EvaluationRunner(self.db)

    def queries(self) -> EvaluationQueries:
        return EvaluationQueries(self.db)


__all__ = [
    "CriterionResultView",
    "EvaluationFacade",
    "EvaluationQueries",
    "EvaluationResultView",
    "EvaluationRunView",
    "EvaluationRunner",
    "ToolOutcomeEvidence",
    "VoiceSessionEvidence",
]
