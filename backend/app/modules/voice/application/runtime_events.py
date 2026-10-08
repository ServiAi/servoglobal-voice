"""Ingest of events posted by voice-runtime for a VoiceSession.

Voice owns the session state: idempotency (event_id), allowlisted payload,
lifecycle transitions and runtime timestamps. Everything downstream (call
history, CRM call status/activity) happens behind VoiceProjectionPort.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.modules.voice.application.ports import VoiceProjectionPort
from app.modules.voice.application.session_service import VoiceSessionService
from app.modules.voice.domain.errors import InvalidRuntimeEventError
from app.modules.voice.domain.lifecycle import (
    RUNTIME_EVENT_TARGETS,
    as_utc,
    can_transition,
)

ALLOWED_PAYLOAD_KEYS = frozenset({
    "livekit_job_id", "provider_session_id", "end_reason", "error_code", "speaker", "text",
    "timestamp", "participant_identity", "track_source", "transcript_final_sequence",
})


class RuntimeEventIngestor:
    def __init__(self, db: Session, projection: VoiceProjectionPort | None = None) -> None:
        self.db = db
        if projection is None:
            from app.modules.voice.wiring import voice_projection

            projection = voice_projection(db)
        self.projection = projection
        self.sessions = VoiceSessionService(db)

    def ingest(
        self,
        session_id: str,
        *,
        event_type: str,
        source: str,
        event_id: str | None,
        sequence: int | None,
        payload: dict[str, Any],
        occurred_at: datetime | None,
    ) -> bool:
        """Records one runtime event; returns True if it was a duplicate.
        Raises VoiceSessionNotFoundError / VoiceSessionError /
        InvalidRuntimeEventError; the caller owns rollback on error."""
        session = self.sessions.get(session_id)
        allowed_payload = {key: value for key, value in payload.items() if key in ALLOWED_PAYLOAD_KEYS}
        if event_id is not None and (not event_id or len(event_id) > 80):
            raise InvalidRuntimeEventError("Invalid runtime event id")
        if event_type == "voice.transcript.final" and (
            allowed_payload.get("speaker") not in {"user", "assistant"}
            or not isinstance(allowed_payload.get("text"), str)
            or not allowed_payload["text"].strip()
            or len(allowed_payload["text"]) > 10000
            or isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence < 1
        ):
            raise InvalidRuntimeEventError("Invalid final transcript")
        if event_type == "voice.session.ended" and "transcript_final_sequence" in allowed_payload and (
            isinstance(allowed_payload["transcript_final_sequence"], bool)
            or not isinstance(allowed_payload["transcript_final_sequence"], int)
            or allowed_payload["transcript_final_sequence"] < 0
        ):
            raise InvalidRuntimeEventError("Invalid final transcript sequence")
        _event, duplicate = self.sessions.record_event(
            session, event_type, source=source, event_id=event_id, sequence=sequence,
            payload=allowed_payload, occurred_at=occurred_at, commit=False,
        )
        if duplicate:
            self.db.rollback()
            self.projection.reconcile(session_id, session.tenant_id)
            return True
        if "livekit_job_id" in allowed_payload:
            session.livekit_job_id = str(allowed_payload["livekit_job_id"])[:160]
        if "provider_session_id" in allowed_payload:
            session.provider_session_id = str(allowed_payload["provider_session_id"])[:255]
        if event_type == "voice.agent.ready" and session.runtime_ready_at is None:
            session.runtime_ready_at = occurred_at or datetime.now(UTC)
        if event_type == "voice.session.ended" and session.status == "connected":
            self.sessions.transition(session, "ending", commit=False)
        target = RUNTIME_EVENT_TARGETS.get(event_type)
        if target and can_transition(session.status, target):
            self.sessions.transition(session, target, commit=False)
        if event_type == "voice.session.started" and session.started_at is not None:
            session.started_at = min(as_utc(session.started_at), as_utc(occurred_at))
        elif event_type == "voice.session.connected" and (
                session.ended_at is None or as_utc(occurred_at) <= as_utc(session.ended_at)):
            session.connected_at = (
                min(as_utc(session.connected_at), as_utc(occurred_at)) if session.connected_at else as_utc(occurred_at)
            )
        elif event_type in {"voice.session.ended", "voice.session.failed"} and session.status in {"ended", "failed"}:
            session.ended_at = (
                min(as_utc(session.ended_at), as_utc(occurred_at)) if session.ended_at else as_utc(occurred_at)
            )
        if event_type == "voice.session.ended":
            session.end_reason = str(allowed_payload.get("end_reason", "unknown"))[:40]
        elif event_type == "voice.session.failed":
            session.error_code = str(allowed_payload.get("error_code", "runtime_failed"))[:80]
        self.projection.on_runtime_event(session_id, session.tenant_id, event_type, occurred_at)
        self.db.commit()
        return False
