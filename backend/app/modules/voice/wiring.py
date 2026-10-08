"""Composition root of Voice Orchestration: binds its ports to other
modules' public APIs. The only file in app.modules.voice allowed to know
which concrete module serves each port."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.analytics.public import VoiceCallProjectionFacade
from app.modules.crm.public import CrmFacade
from app.modules.voice.application.ports import CrmContextPort, VoiceProjectionPort


def crm_context(db: Session) -> CrmContextPort:
    return CrmFacade(db)


def voice_projection(db: Session) -> VoiceProjectionPort:
    return VoiceCallProjectionFacade(db)


class _EvaluationRequestAdapter:
    def __init__(self, db: Session) -> None:
        self.db = db

    def request_terminal_session(
        self,
        *,
        tenant_id: str,
        session_id: str,
        purpose: str,
        status: str,
        agent_version_id: str | None,
        ended_at,
        error_code: str | None,
        tool_outcomes: tuple[dict, ...],
    ) -> None:
        from app.modules.evaluations.public import (
            EvaluationRunner,
            ToolOutcomeEvidence,
            VoiceSessionEvidence,
        )

        evidence = VoiceSessionEvidence(
            tenant_id=tenant_id,
            session_id=session_id,
            purpose=purpose,
            status=status,
            agent_version_id=agent_version_id,
            ended_at=ended_at,
            error_code=error_code,
            tool_outcomes=tuple(ToolOutcomeEvidence(**item) for item in tool_outcomes),
        )
        EvaluationRunner(self.db).request_voice_session(
            evidence, trigger_key=f"voice.session.terminal:{session_id}"
        )


def evaluation_requests(db: Session):
    return _EvaluationRequestAdapter(db)
