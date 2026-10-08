from __future__ import annotations

from app.modules.evaluations.application.contracts import EvaluationRunView
from app.modules.evaluations.domain.technical_health import VoiceSessionEvidence


class EvaluationRequestService:
    """Application use case; persistence is supplied by the composition root."""

    def __init__(self, repository: object) -> None:
        self.repository = repository

    def request_voice_session(self, evidence: VoiceSessionEvidence, *, trigger_key: str) -> EvaluationRunView:
        return self.repository.request_voice_session(evidence, trigger_key=trigger_key)
