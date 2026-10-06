"""Project a real voice session into call history and, when linked, the CRM call/activity.

Voice, CRM and Agents are reached only through ports (see ``ports.py``). Transaction rule:
``project_session(commit=False)`` flushes and the caller owns the commit."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.analytics.application.agent_service import AnalyticsAgentService
from app.modules.analytics.application.ports import (
    AgentCatalogPort,
    CallActivity,
    CrmCallProjectionPort,
    ProjectionCrmCall,
    ProjectionEvent,
    ProjectionLead,
    ProjectionSession,
    VoiceSessionProjectionPort,
)
from app.modules.analytics.application.views import call_view
from app.modules.analytics.contracts import AgentUpsertCommand, CallView
from app.modules.analytics.infrastructure.models import Call

logger = logging.getLogger(__name__)

RUNTIME_PROVIDER = "serviglobal_voice_runtime"
REAL_EVENTS = {
    "voice.participant.connected",
    "voice.audio.input.started",
    "voice.session.connected",
    "voice.transcript.final",
    "voice.audio.output.started",
}
TERMINAL_STATUSES = {"ended", "failed", "cancelled"}
TERMINAL_CRM_STATUSES = {"completed", "failed", "cancelled", "no_answer", "busy", "rejected"}
_CRM_OPEN_FINAL = {"busy", "rejected", "no_answer", "failed", "completed"}


class VoiceCallProjectionService:
    def __init__(
        self,
        db: Session,
        *,
        sessions: VoiceSessionProjectionPort,
        crm: CrmCallProjectionPort,
        agent_catalog: AgentCatalogPort,
    ) -> None:
        self.db = db
        self.sessions = sessions
        self.crm = crm
        self.agent_catalog = agent_catalog

    def _crm_call(self, session: ProjectionSession) -> ProjectionCrmCall | None:
        if not session.crm_voice_call_id:
            return None
        call = self.crm.get_call(session.crm_voice_call_id)
        return call if call is not None and call.tenant_id == session.tenant_id else None

    @staticmethod
    def _is_real(session: ProjectionSession, crm_call: ProjectionCrmCall | None) -> bool:
        crm_operational = bool(
            crm_call
            and (crm_call.started_at or crm_call.provider_attempt_started_at or crm_call.answered_at or session.sip_call_id)
        )
        return crm_operational or any(event.event_type in REAL_EVENTS for event in session.events)

    def is_real_call(self, session_id: str, tenant_id: str | None = None) -> bool:
        """Read-only preview of project_session's eligibility (no row locks)."""
        session = self.sessions.get_session(session_id, tenant_id, lock=False)
        return self._is_real(session, self._crm_call(session))

    def projection_exists(self, session_id: str, tenant_id: str) -> bool:
        return (
            self.db.scalar(
                select(Call.id).where(Call.tenant_id == tenant_id, Call.external_call_id == f"voice-session:{session_id}")
            )
            is not None
        )

    def project_session(self, session_id: str, *, tenant_id: str | None = None, commit: bool = True) -> CallView | None:
        session = self.sessions.get_session(session_id, tenant_id)
        events = list(session.events)
        crm_call = self._crm_call(session)
        if not self._is_real(session, crm_call):
            return None

        started_at = self._utc(
            crm_call.started_at
            if crm_call and crm_call.started_at
            else self._first(events, "voice.session.started") or session.started_at or session.requested_at
        )
        connected_at = self._utc(
            (crm_call.answered_at if crm_call else None) or self._first(events, "voice.session.connected") or session.connected_at
        )
        ended_at = self._utc(
            (crm_call.ended_at if crm_call else None)
            or session.ended_at
            or self._first(events, "voice.session.ended", "voice.session.failed")
        )
        crm_status = crm_call.status if crm_call else None
        terminal = session.status in TERMINAL_STATUSES or crm_status in TERMINAL_CRM_STATUSES
        normalized_status = self._status(session.status, crm_status, connected_at, terminal)
        duration = None
        if terminal:
            duration = (
                max(0, int((ended_at - connected_at).total_seconds()))
                if connected_at and ended_at
                else 0
                if not connected_at
                else None
            )

        agent_id = self._agent_id(session)
        provider = session.provider or "unknown"
        call = self._locked_call(session.tenant_id, f"voice-session:{session.id}", provider, started_at, normalized_status)
        call.agent_id = agent_id
        call.external_provider = provider
        call.provider_agent_id = session.agent_id or session.deleted_agent_id
        call.provider_status = crm_status or session.status
        call.normalized_status = normalized_status
        call.started_at = started_at
        call.joined_at = connected_at
        call.ended_at = ended_at if terminal else None
        call.duration_seconds = duration
        call.direction = session.direction
        call.channel = session.channel
        call.summary = crm_call.summary if crm_call else None
        call.recording_url = crm_call.recording_url if crm_call else None
        call.last_synced_at = datetime.now(UTC)
        self.db.flush()

        if crm_call is not None:
            changes: dict[str, object] = {
                "provider_session_id": session.provider_session_id or crm_call.provider_session_id
            }
            if terminal and crm_call.status == "completed" and not connected_at:
                changes["status"] = "no_answer"
            changes["duration_seconds"] = duration
            if terminal and crm_call.ended_at is None:
                changes["ended_at"] = ended_at
            crm_call = self.crm.update_call(crm_call.id, changes)

        self._activity(session, crm_call, call, events)
        if commit:
            self.db.commit()
            self.db.refresh(call)
        return call_view(call)

    def apply_runtime_event(
        self, session_id: str, tenant_id: str, event_type: str, occurred_at: datetime | None
    ) -> CallView | None:
        """CRM call status for a runtime event, then the projection; inside the caller's transaction."""
        session = self.sessions.get_session(session_id, tenant_id)
        if session.crm_voice_call_id:
            call = self.crm.get_call(session.crm_voice_call_id)
            if call is not None and call.tenant_id == session.tenant_id:
                now = occurred_at or datetime.now(UTC)
                if event_type == "voice.session.connected" and call.status == "answered":
                    self.crm.update_call(call.id, {"status": "in_progress"})
                elif event_type == "voice.session.ended" and call.status not in _CRM_OPEN_FINAL:
                    self.crm.update_call(
                        call.id, {"status": "completed" if call.answered_at else "no_answer", "ended_at": now}
                    )
                    logger.info(
                        "LiveKit SIP outbound completed | tenant_id=%s | crm_voice_call_id=%s | voice_session_id=%s | livekit_room_name=%s | livekit_dispatch_id=%s | livekit_sip_trunk_id=%s | sip_participant_identity=%s | sip_call_id=%s",
                        session.tenant_id,
                        call.id,
                        session.id,
                        session.livekit_room_name,
                        session.livekit_dispatch_id,
                        session.livekit_sip_trunk_id,
                        session.livekit_sip_participant_identity,
                        session.sip_call_id,
                    )
                elif event_type == "voice.session.failed" and call.status not in _CRM_OPEN_FINAL:
                    self.crm.update_call(call.id, {"status": "failed", "ended_at": now})
        self.db.flush()
        return self.project_session(session_id, tenant_id=tenant_id, commit=False)

    def reconcile_session(self, session_id: str, *, tenant_id: str | None = None) -> CallView | None:
        return self.project_session(session_id, tenant_id=tenant_id)

    def _locked_call(
        self, tenant_id: str, external_call_id: str, provider: str, started_at: datetime, normalized_status: str
    ) -> Call:
        """The projected call, locked; created once even when two projections race (the unique
        (tenant, provider, external_call_id) decides the winner and the loser reuses it)."""
        statement = select(Call).where(Call.tenant_id == tenant_id, Call.external_call_id == external_call_id)
        call = self.db.scalar(statement.with_for_update())
        if call is not None:
            return call
        call = Call(
            tenant_id=tenant_id,
            external_provider=provider,
            external_call_id=external_call_id,
            started_at=started_at,
            normalized_status=normalized_status,
        )
        try:
            with self.db.begin_nested():
                self.db.add(call)
                self.db.flush()
        except IntegrityError:
            winner = self.db.scalar(statement.with_for_update())
            if winner is None:
                raise
            return winner
        return call

    def _agent_id(self, session: ProjectionSession) -> str | None:
        canonical_id = session.agent_id or session.deleted_agent_id
        if canonical_id is None:
            return None
        display = self.agent_catalog.describe_agent(session.tenant_id, canonical_id, session.agent_version_id)
        agent = AnalyticsAgentService(self.db).upsert_provider_agent(
            AgentUpsertCommand(
                tenant_id=session.tenant_id,
                external_provider=RUNTIME_PROVIDER,
                external_agent_id=canonical_id,
                name=display.name or "Agente de voz",
                status=display.status or "archived",
                channel_type="voice",
            )
        )
        return agent.id

    def _activity(
        self, session: ProjectionSession, crm_call: ProjectionCrmCall | None, call: Call, events: list[ProjectionEvent]
    ) -> None:
        contact_id = (crm_call.contact_id if crm_call else None) or session.context_contact_id
        lead_id = (crm_call.lead_id if crm_call else None) or session.context_lead_id
        lead = self.crm.get_lead(session.tenant_id, lead_id) if lead_id else None
        if lead_id and lead is None:
            return
        if lead and not contact_id:
            contact_id = lead.contact_id
        if not contact_id:
            return
        if not self.crm.contact_exists(session.tenant_id, contact_id):
            return
        if lead and lead.contact_id != contact_id:
            return

        transcript = [
            {
                "event_id": event.event_id,
                "sequence": event.sequence,
                "occurred_at": self._utc(event.occurred_at).isoformat(),
                "speaker": event.speaker,
                "text": event.text,
            }
            for event in sorted(
                events, key=lambda item: (item.sequence is None, item.sequence or 0, item.occurred_at, item.event_id)
            )
            if event.event_type == "voice.transcript.final"
            and event.speaker in {"user", "assistant"}
            and isinstance(event.text, str)
            and event.text.strip()
        ]
        self.crm.upsert_call_activity(
            CallActivity(
                tenant_id=session.tenant_id,
                call_id=call.id,
                deduplication_key=f"voice_session:{session.id}",
                contact_id=contact_id,
                lead_id=lead.id if lead else None,
                title="Llamada de voz IA",
                occurred_at=call.started_at,
                outcome=call.normalized_status,
                payload={
                    "voice_session_id": session.id,
                    "crm_voice_call_id": crm_call.id if crm_call else None,
                    "provider": call.external_provider,
                    "channel": session.channel,
                    "direction": session.direction,
                    "status": call.normalized_status,
                    "duration_seconds": call.duration_seconds,
                    "summary": call.summary,
                    "recording_url": call.recording_url,
                    "transcript": transcript,
                },
            )
        )
        if lead and (lead.last_call_id is None or self._newer_call(lead, call)):
            self.crm.set_lead_last_call(session.tenant_id, lead.id, call.id)

    def _newer_call(self, lead: ProjectionLead, call: Call) -> bool:
        previous = self.db.scalar(select(Call).where(Call.id == lead.last_call_id, Call.tenant_id == call.tenant_id))
        return previous is None or (self._utc(call.started_at), call.id) >= (self._utc(previous.started_at), previous.id)

    @staticmethod
    def _utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @staticmethod
    def _first(events: list[ProjectionEvent], *types: str) -> datetime | None:
        return min(
            (VoiceCallProjectionService._utc(event.occurred_at) for event in events if event.event_type in types),
            default=None,
        )

    @staticmethod
    def _status(session_status: str, crm_status: str | None, connected_at: datetime | None, terminal: bool) -> str:
        if crm_status in {"busy", "rejected"}:
            return "rejected"
        if crm_status == "no_answer":
            return "unanswered"
        if crm_status == "cancelled" or session_status == "cancelled":
            return "cancelled"
        if crm_status == "failed" or session_status == "failed":
            return "failed"
        if terminal:
            return "answered" if connected_at else "unanswered"
        return "in_progress"
