"""Implementation behind voice.public.VoiceSessionFacade (loaded lazily so
importing voice.public stays light)."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.agents.public import AgentsFacade
from app.modules.crm.public import ContactRef, LeadRef
from app.modules.voice.application.session_service import VoiceSessionService
from app.modules.voice.domain.errors import VoiceSessionError, VoiceSessionNotFoundError
from app.modules.voice.domain.session_context import SessionContextV1
from app.modules.voice.domain.views import (
    SessionEventFact,
    SessionProjectionFacts,
    ToolSessionView,
    VoiceSessionRef,
    WebRTCJoinInfo,
)
from app.modules.voice.infrastructure.models import VoiceSession, VoiceSessionEvent


class VoiceSessionOperations:
    def __init__(self, db: Session, runtime_backend: Any = None) -> None:
        self.db = db
        self.runtime_backend = runtime_backend
        self.sessions = VoiceSessionService(db)

    def create_session_from_agent_version(
        self, tenant_id: str, agent_id: str, agent_version_id: str, **options: Any
    ) -> VoiceSessionRef:
        session = self.sessions.create_from_agent_version(tenant_id, agent_id, agent_version_id, **options)
        return VoiceSessionRef(
            session_id=session.id, tenant_id=session.tenant_id, agent_id=session.agent_id,
            agent_version_id=session.agent_version_id, channel=session.channel, direction=session.direction,
            purpose=session.purpose, status=session.status, pipeline_type=session.pipeline_type,
            provider=session.provider,
        )

    def attach_crm_call(self, session_id: str, tenant_id: str, crm_voice_call_id: str) -> None:
        """Correlates the session with its CRM call (commits). Idempotent; a different
        call id, another tenant's session or a missing/foreign CRM call is rejected."""
        from app.modules.crm.public import CrmVoiceCalls

        call = CrmVoiceCalls(self.db).get(crm_voice_call_id)
        if call is None or call.tenant_id != tenant_id:
            raise VoiceSessionError("crm_voice_call_not_found")
        session = self.db.scalar(
            select(VoiceSession)
            .where(VoiceSession.id == session_id, VoiceSession.tenant_id == tenant_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if session is None:
            raise VoiceSessionNotFoundError("Voice session not found.")
        if session.crm_voice_call_id not in (None, crm_voice_call_id):
            raise VoiceSessionError("crm_voice_call_conflict")
        session.crm_voice_call_id = crm_voice_call_id
        self.db.commit()

    async def ensure_webrtc_join(self, session_id: str, tenant_id: str) -> WebRTCJoinInfo:
        from app.modules.voice.application.webrtc import WebRTCJoinService

        return await WebRTCJoinService(self.db, self.runtime_backend).ensure_join(session_id, tenant_id)

    def get_tool_session(self, session_id: str) -> ToolSessionView:
        session = self.sessions.get(session_id)
        agents = AgentsFacade(self.db)
        return ToolSessionView(
            id=session.id,
            tenant_id=session.tenant_id,
            status=session.status,
            agent_id=session.agent_id,
            agent_status=agents.get_agent_status(session.tenant_id, session.agent_id) if session.agent_id else None,
            tool_bindings=(
                agents.get_tool_bindings(session.tenant_id, session.agent_version_id)
                if session.agent_version_id
                else ()
            ),
            context=SessionContextV1.model_validate(session.session_context_json or {}),
        )

    def read_conversation_evidence(self, tenant_id: str, session_id: str):
        from app.modules.voice.domain.errors import VoiceConversationEvidenceNotReadyError
        from app.modules.voice.domain.lifecycle import TERMINAL_STATUSES
        from app.modules.voice.domain.views import (
            TranscriptCompleteness,
            TranscriptTurn,
            VoiceConversationEvidence,
            VoiceToolOutcome,
        )

        session = self.db.scalar(select(VoiceSession).where(
            VoiceSession.id == session_id,
            VoiceSession.tenant_id == tenant_id,
        ))
        if session is None:
            raise VoiceSessionNotFoundError("Voice session not found for tenant.")
        if session.status not in TERMINAL_STATUSES:
            raise VoiceConversationEvidenceNotReadyError("evidence_not_ready")
        events = self.db.scalars(select(VoiceSessionEvent).where(
            VoiceSessionEvent.tenant_id == tenant_id,
            VoiceSessionEvent.voice_session_id == session_id,
        )).all()
        transcript = [event for event in events if event.event_type == "voice.transcript.final"]
        turns_valid = all(
            event.payload_json.get("speaker") in {"user", "assistant"}
            and isinstance(event.payload_json.get("text"), str)
            and bool(event.payload_json["text"].strip())
            for event in transcript
        )
        turns = tuple(
            TranscriptTurn(
                event_id=event.event_id,
                sequence=event.sequence,
                speaker=event.payload_json["speaker"],
                text=event.payload_json["text"],
                occurred_at=event.occurred_at,
            )
            for event in sorted(
                transcript,
                key=lambda row: (row.sequence is None, row.sequence or 0, row.occurred_at, row.event_id),
            )
            if event.payload_json.get("speaker") in {"user", "assistant"}
            and isinstance(event.payload_json.get("text"), str)
            and event.payload_json["text"].strip()
        )
        markers = [
            event.payload_json.get("transcript_final_sequence")
            for event in events
            if event.event_type == "voice.session.ended"
            and event.source == "voice-runtime"
            and "transcript_final_sequence" in event.payload_json
        ]
        completeness = TranscriptCompleteness.NOT_AVAILABLE
        if markers:
            expected = markers[0]
            actual = [
                event.sequence
                for event in sorted(
                    transcript,
                    key=lambda row: (row.sequence is None, row.sequence or 0, row.occurred_at, row.event_id),
                )
            ]
            completeness = TranscriptCompleteness.INCOMPLETE
            if (
                len(markers) == 1
                and isinstance(expected, int)
                and not isinstance(expected, bool)
                and expected >= 0
                and turns_valid
                and actual == list(range(1, expected + 1))
            ):
                completeness = TranscriptCompleteness.COMPLETE
        outcomes = tuple(
            VoiceToolOutcome(
                event_id=event.event_id,
                tool_key=payload["tool_key"],
                status=payload["status"],
                duration_ms=payload["duration_ms"],
                error_code=(
                    payload.get("error_code")
                    if isinstance(payload.get("error_code"), str)
                    and len(payload["error_code"]) <= 80
                    and payload["error_code"].replace("_", "").isalnum()
                    else None
                ),
            )
            for event in sorted(events, key=lambda row: (row.occurred_at, row.event_id))
            if event.event_type == "session.context.tool_used"
            for payload in (event.payload_json or {},)
            if isinstance(payload.get("tool_key"), str)
            and payload.get("status") in {"success", "error"}
            and isinstance(payload.get("duration_ms"), int)
            and not isinstance(payload.get("duration_ms"), bool)
        )
        return VoiceConversationEvidence(
            tenant_id=session.tenant_id,
            session_id=session.id,
            purpose=session.purpose,
            terminal_status=session.status,
            ended_at=session.ended_at,
            agent_version_id=session.agent_version_id or session.deleted_agent_version_id,
            transcript_completeness=completeness,
            turns=turns,
            tool_outcomes=outcomes,
        )

    def record_event(self, session_id: str, event_type: str, *, source: str, payload: dict[str, Any]) -> None:
        self.sessions.record_event(self.sessions.get(session_id), event_type, source=source, payload=payload)

    def enrich_context(
        self, session_id: str, *, contact: ContactRef | None, lead: LeadRef | None, event_source: str
    ) -> None:
        self.sessions.enrich_context_by_ids(
            self.sessions.get(session_id),
            contact_id=contact.id if contact else None,
            lead_id=lead.id if lead else None,
            event_source=event_source,
        )

    async def release_sessions_of_deleted_agent(self, tenant_id: str, agent_id: str) -> None:
        await self.sessions.release_sessions_of_deleted_agent(tenant_id, agent_id)

    def get_projection_facts(
        self, session_id: str, tenant_id: str | None, *, lock: bool = True
    ) -> SessionProjectionFacts:
        """Locks the session row (SELECT ... FOR UPDATE) for the caller's
        transaction, like the projection always did; ``lock=False`` is for
        read-only previews (dry runs) that must not hold row locks."""
        query = select(VoiceSession).where(VoiceSession.id == session_id)
        if lock:
            query = query.with_for_update()
        if tenant_id is not None:
            query = query.where(VoiceSession.tenant_id == tenant_id)
        session = self.db.scalar(query)
        if session is None:
            raise VoiceSessionNotFoundError("Voice session not found for tenant.")
        events = self.db.scalars(select(VoiceSessionEvent).where(
            VoiceSessionEvent.tenant_id == session.tenant_id,
            VoiceSessionEvent.voice_session_id == session.id,
        )).all()
        return SessionProjectionFacts(
            id=session.id,
            tenant_id=session.tenant_id,
            status=session.status,
            agent_id=session.agent_id,
            deleted_agent_id=session.deleted_agent_id,
            agent_version_id=session.agent_version_id,
            provider=session.provider,
            provider_session_id=session.provider_session_id,
            channel=session.channel,
            direction=session.direction,
            crm_voice_call_id=session.crm_voice_call_id,
            requested_at=session.requested_at,
            started_at=session.started_at,
            connected_at=session.connected_at,
            ended_at=session.ended_at,
            context=SessionContextV1.model_validate(session.session_context_json or {}),
            livekit_room_name=session.livekit_room_name,
            livekit_dispatch_id=session.livekit_dispatch_id,
            livekit_sip_trunk_id=session.livekit_sip_trunk_id,
            livekit_sip_participant_identity=session.livekit_sip_participant_identity,
            sip_call_id=session.sip_call_id,
            events=tuple(
                SessionEventFact(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    sequence=event.sequence,
                    occurred_at=event.occurred_at,
                    payload=MappingProxyType(dict(event.payload_json or {})),
                )
                for event in events
            ),
        )

    def list_projection_candidates(
        self, *, after_id: str, limit: int, tenant_id: str | None = None
    ) -> list[tuple[str, str]]:
        """Next page of (session_id, tenant_id) of real-channel (sip/webrtc)
        sessions ordered by id, for projection reconciliation."""
        query = (
            select(VoiceSession.id, VoiceSession.tenant_id)
            .where(VoiceSession.id > after_id, VoiceSession.channel.in_(("sip", "webrtc")))
            .order_by(VoiceSession.id)
            .limit(limit)
        )
        if tenant_id:
            query = query.where(VoiceSession.tenant_id == tenant_id)
        return [(row[0], row[1]) for row in self.db.execute(query).all()]

    def agent_ids_by_crm_call(self, tenant_id: str, crm_voice_call_ids: list[str]) -> dict[str, str | None]:
        """crm_voice_call_id -> agent_id for the sessions correlated to those
        CRM calls (call-history view)."""
        if not crm_voice_call_ids:
            return {}
        rows = self.db.execute(
            select(VoiceSession.crm_voice_call_id, VoiceSession.agent_id).where(
                VoiceSession.tenant_id == tenant_id,
                VoiceSession.crm_voice_call_id.in_(crm_voice_call_ids),
            )
        ).all()
        return {row[0]: row[1] for row in rows}
