"""Project a real VoiceSession into analytics and, when linked, the CRM.

Legacy projection adapter (owned by Analytics/CRM, not by Voice): it reads
the session only as voice.public.SessionProjectionFacts and is reached by
Voice through analytics.public.VoiceCallProjectionFacade.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.analytics import Agent, Call
from app.models.crm import CrmActivity, CrmContact, CrmLead, CrmVoiceCall
from app.modules.agents.public import AgentsFacade
from app.modules.voice.public import (
    SessionEventFact,
    SessionProjectionFacts,
    VoiceSessionFacade,
)

logger = logging.getLogger(__name__)


REAL_EVENTS = {
    "voice.participant.connected",
    "voice.audio.input.started",
    "voice.session.connected",
    "voice.transcript.final",
    "voice.audio.output.started",
}
TERMINAL_STATUSES = {"ended", "failed", "cancelled"}
TERMINAL_CRM_STATUSES = {"completed", "failed", "cancelled", "no_answer", "busy", "rejected"}


class VoiceCallProjectionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _crm_call(self, session: SessionProjectionFacts) -> CrmVoiceCall | None:
        return self.db.scalar(select(CrmVoiceCall).where(
            CrmVoiceCall.id == session.crm_voice_call_id,
            CrmVoiceCall.tenant_id == session.tenant_id,
        )) if session.crm_voice_call_id else None

    @staticmethod
    def _is_real(session: SessionProjectionFacts, crm_call: CrmVoiceCall | None) -> bool:
        crm_operational = bool(crm_call and (crm_call.started_at or crm_call.provider_attempt_started_at
                                             or crm_call.answered_at or session.sip_call_id))
        return crm_operational or any(event.event_type in REAL_EVENTS for event in session.events)

    def is_real_call(self, session_id: str, tenant_id: str | None = None) -> bool:
        """Read-only preview of project_session's eligibility (no row locks)."""
        session = VoiceSessionFacade(self.db).get_projection_facts(session_id, tenant_id, lock=False)
        return self._is_real(session, self._crm_call(session))

    def projection_exists(self, session_id: str, tenant_id: str) -> bool:
        return self.db.scalar(select(Call.id).where(
            Call.tenant_id == tenant_id,
            Call.external_call_id == f"voice-session:{session_id}",
        )) is not None

    def project_session(self, session_id: str, *, tenant_id: str | None = None, commit: bool = True) -> Call | None:
        session = VoiceSessionFacade(self.db).get_projection_facts(session_id, tenant_id)
        events = list(session.events)
        crm_call = self._crm_call(session)
        if not self._is_real(session, crm_call):
            return None

        started_at = self._utc(crm_call.started_at if crm_call and crm_call.started_at else self._first(events, "voice.session.started") or session.started_at or session.requested_at)
        connected_at = self._utc((crm_call.answered_at if crm_call else None) or self._first(events, "voice.session.connected") or session.connected_at)
        ended_at = self._utc((crm_call.ended_at if crm_call else None) or session.ended_at or self._first(events, "voice.session.ended", "voice.session.failed"))
        crm_status = crm_call.status if crm_call else None
        terminal = session.status in TERMINAL_STATUSES or crm_status in TERMINAL_CRM_STATUSES
        normalized_status = self._status(session.status, crm_status, connected_at, terminal)
        duration = None
        if terminal:
            duration = max(0, int((ended_at - connected_at).total_seconds())) if connected_at and ended_at else 0 if not connected_at else None

        agent = self._agent(session)
        external_id = f"voice-session:{session.id}"
        provider = session.provider or "unknown"
        call = self.db.scalar(select(Call).where(
            Call.tenant_id == session.tenant_id,
            Call.external_call_id == external_id,
        ).with_for_update())
        if call is None:
            call = Call(tenant_id=session.tenant_id, external_provider=provider, external_call_id=external_id,
                        started_at=started_at, normalized_status=normalized_status)
            self.db.add(call)
        call.agent_id = agent.id if agent else None
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
            crm_call.provider_session_id = session.provider_session_id or crm_call.provider_session_id
            if terminal and crm_call.status == "completed" and not connected_at:
                crm_call.status = "no_answer"
            crm_call.duration_seconds = duration
            if terminal and crm_call.ended_at is None:
                crm_call.ended_at = ended_at

        self._activity(session, crm_call, call, events)
        if commit:
            self.db.commit()
            self.db.refresh(call)
        return call

    def apply_runtime_event(
        self, session_id: str, tenant_id: str, event_type: str, occurred_at: datetime | None
    ) -> Call | None:
        """CRM call status for a runtime event, then the projection; inside
        the caller's transaction (no commit)."""
        session = VoiceSessionFacade(self.db).get_projection_facts(session_id, tenant_id)
        if session.crm_voice_call_id:
            call = self.db.get(CrmVoiceCall, session.crm_voice_call_id)
            if call is not None and call.tenant_id == session.tenant_id:
                now = occurred_at or datetime.now(UTC)
                if event_type == "voice.session.connected" and call.status == "answered":
                    call.status = "in_progress"
                elif event_type == "voice.session.ended" and call.status not in {
                    "busy", "rejected", "no_answer", "failed", "completed"
                }:
                    call.status = "completed" if call.answered_at else "no_answer"
                    call.ended_at = now
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
                elif event_type == "voice.session.failed" and call.status not in {
                    "busy", "rejected", "no_answer", "failed", "completed"
                }:
                    call.status = "failed"
                    call.ended_at = now
        self.db.flush()
        return self.project_session(session_id, tenant_id=tenant_id, commit=False)

    def reconcile_session(self, session_id: str, *, tenant_id: str | None = None) -> Call | None:
        return self.project_session(session_id, tenant_id=tenant_id)

    def _agent(self, session: SessionProjectionFacts) -> Agent | None:
        canonical_id = session.agent_id or session.deleted_agent_id
        if canonical_id is None:
            return None
        agent = self.db.scalar(select(Agent).where(
            Agent.tenant_id == session.tenant_id,
            Agent.external_provider == "serviglobal_voice_runtime",
            Agent.external_agent_id == canonical_id,
        ).with_for_update())
        display = AgentsFacade(self.db).describe_agent(session.tenant_id, canonical_id, session.agent_version_id)
        name = display.name or "Agente de voz"
        status = display.status or "archived"
        if agent is None and self.db.get_bind().dialect.name == "postgresql":
            self.db.execute(pg_insert(Agent).values(
                tenant_id=session.tenant_id,
                external_provider="serviglobal_voice_runtime",
                external_agent_id=canonical_id,
                name=name,
                channel_type="voice",
                status=status,
            ).on_conflict_do_nothing(constraint="uq_agents_tenant_provider_external_agent"))
            agent = self.db.scalar(select(Agent).where(
                Agent.tenant_id == session.tenant_id,
                Agent.external_provider == "serviglobal_voice_runtime",
                Agent.external_agent_id == canonical_id,
            ))
        if agent is None:
            agent = Agent(tenant_id=session.tenant_id, external_provider="serviglobal_voice_runtime",
                          external_agent_id=canonical_id, name=name, channel_type="voice",
                          status=status)
            self.db.add(agent)
            self.db.flush()
        else:
            agent.name = name
            agent.status = status
        return agent

    def _activity(self, session: SessionProjectionFacts, crm_call: CrmVoiceCall | None, call: Call,
                  events: list[SessionEventFact]) -> None:
        context = session.context
        contact_id = (crm_call.contact_id if crm_call else None) or (context.contact.id if context.contact else None)
        lead_id = (crm_call.lead_id if crm_call else None) or (context.lead.id if context.lead else None)
        lead = self.db.scalar(select(CrmLead).where(
            CrmLead.id == lead_id, CrmLead.tenant_id == session.tenant_id,
        )) if lead_id else None
        if lead_id and lead is None:
            return
        if lead and not contact_id:
            contact_id = lead.contact_id
        if not contact_id:
            return
        contact = self.db.scalar(select(CrmContact).where(CrmContact.id == contact_id,
                                                          CrmContact.tenant_id == session.tenant_id))
        if contact is None:
            return
        if lead and lead.contact_id != contact.id:
            return

        transcript = [
            {"event_id": event.event_id, "sequence": event.sequence,
             "occurred_at": self._utc(event.occurred_at).isoformat(), "speaker": event.payload["speaker"],
             "text": event.payload["text"]}
            for event in sorted(events, key=lambda item: (item.sequence is None, item.sequence or 0,
                                                           item.occurred_at, item.event_id))
            if event.event_type == "voice.transcript.final"
            and event.payload.get("speaker") in {"user", "assistant"}
            and isinstance(event.payload.get("text"), str)
            and event.payload["text"].strip()
        ]
        key = f"voice_session:{session.id}"
        activity = self.db.scalar(select(CrmActivity).where(
            CrmActivity.tenant_id == session.tenant_id,
            CrmActivity.call_id == call.id,
            CrmActivity.activity_type == "voice_call",
            CrmActivity.deduplication_key == key,
        ).with_for_update())
        if activity is None:
            activity = CrmActivity(tenant_id=session.tenant_id, contact_id=contact.id,
                                   activity_type="voice_call", call_id=call.id,
                                   deduplication_key=key, title="Llamada de voz IA")
            self.db.add(activity)
        activity.lead_id = lead.id if lead else None
        activity.occurred_at = call.started_at
        activity.outcome = call.normalized_status
        activity.payload_json = {
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
        }
        if lead and (lead.last_call_id is None or self._newer_call(lead, call)):
            lead.last_call_id = call.id

    def _newer_call(self, lead: CrmLead, call: Call) -> bool:
        previous = self.db.scalar(select(Call).where(Call.id == lead.last_call_id,
                                                     Call.tenant_id == call.tenant_id))
        return previous is None or (self._utc(call.started_at), call.id) >= (self._utc(previous.started_at), previous.id)

    @staticmethod
    def _utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @staticmethod
    def _first(events: list[SessionEventFact], *types: str) -> datetime | None:
        return min((VoiceCallProjectionService._utc(event.occurred_at) for event in events
                    if event.event_type in types), default=None)

    @staticmethod
    def _status(session_status: str, crm_status: str | None, connected_at: datetime | None,
                terminal: bool) -> str:
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
