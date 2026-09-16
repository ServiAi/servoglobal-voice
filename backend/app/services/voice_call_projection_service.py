"""Project a real VoiceSession into analytics and, when linked, the CRM."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.agents import TenantAgent, TenantAgentVersion
from app.models.analytics import Agent, Call
from app.models.crm import CrmActivity, CrmContact, CrmLead, CrmVoiceCall
from app.models.voice_sessions import VoiceSession, VoiceSessionEvent


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

    def project_session(self, session_id: str, *, tenant_id: str | None = None, commit: bool = True) -> Call | None:
        query = select(VoiceSession).where(VoiceSession.id == session_id).with_for_update()
        if tenant_id is not None:
            query = query.where(VoiceSession.tenant_id == tenant_id)
        session = self.db.scalar(query)
        if session is None:
            raise ValueError("Voice session not found for tenant.")

        events = list(self.db.scalars(select(VoiceSessionEvent).where(
            VoiceSessionEvent.tenant_id == session.tenant_id,
            VoiceSessionEvent.voice_session_id == session.id,
        )).all())
        crm_call = self.db.scalar(select(CrmVoiceCall).where(
            CrmVoiceCall.id == session.crm_voice_call_id,
            CrmVoiceCall.tenant_id == session.tenant_id,
        )) if session.crm_voice_call_id else None
        crm_operational = bool(crm_call and (crm_call.started_at or crm_call.provider_attempt_started_at
                                             or crm_call.answered_at or session.sip_call_id))
        if not crm_operational and not any(event.event_type in REAL_EVENTS for event in events):
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

    def project_event(self, session_id: str, event: VoiceSessionEvent, *, commit: bool = True) -> Call | None:
        if event.voice_session_id != session_id:
            raise ValueError("Event does not belong to voice session.")
        return self.project_session(session_id, tenant_id=event.tenant_id, commit=commit)

    def reconcile_session(self, session_id: str, *, tenant_id: str | None = None) -> Call | None:
        return self.project_session(session_id, tenant_id=tenant_id)

    def _agent(self, session: VoiceSession) -> Agent | None:
        canonical_id = session.agent_id or session.deleted_agent_id
        if canonical_id is None:
            return None
        agent = self.db.scalar(select(Agent).where(
            Agent.tenant_id == session.tenant_id,
            Agent.external_provider == "serviglobal_voice_runtime",
            Agent.external_agent_id == canonical_id,
        ).with_for_update())
        canonical = self.db.scalar(select(TenantAgent).where(
            TenantAgent.id == canonical_id, TenantAgent.tenant_id == session.tenant_id,
        ))
        version = self.db.scalar(select(TenantAgentVersion).where(
            TenantAgentVersion.id == session.agent_version_id,
            TenantAgentVersion.tenant_id == session.tenant_id,
        )) if session.agent_version_id else None
        name = (canonical.name if canonical else (version.identity_json or {}).get("name") if version else None) or "Agente de voz"
        if agent is None and self.db.get_bind().dialect.name == "postgresql":
            self.db.execute(pg_insert(Agent).values(
                tenant_id=session.tenant_id,
                external_provider="serviglobal_voice_runtime",
                external_agent_id=canonical_id,
                name=name,
                channel_type="voice",
                status=canonical.status if canonical else "archived",
            ).on_conflict_do_nothing(constraint="uq_agents_tenant_provider_external_agent"))
            agent = self.db.scalar(select(Agent).where(
                Agent.tenant_id == session.tenant_id,
                Agent.external_provider == "serviglobal_voice_runtime",
                Agent.external_agent_id == canonical_id,
            ))
        if agent is None:
            agent = Agent(tenant_id=session.tenant_id, external_provider="serviglobal_voice_runtime",
                          external_agent_id=canonical_id, name=name, channel_type="voice",
                          status=canonical.status if canonical else "archived")
            self.db.add(agent)
            self.db.flush()
        else:
            agent.name = name
            agent.status = canonical.status if canonical else "archived"
        return agent

    def _activity(self, session: VoiceSession, crm_call: CrmVoiceCall | None, call: Call,
                  events: list[VoiceSessionEvent]) -> None:
        context = session.session_context_json or {}
        contact_data = context.get("contact") or {}
        lead_data = context.get("lead") or {}
        contact_id = (crm_call.contact_id if crm_call else None) or contact_data.get("id")
        lead_id = (crm_call.lead_id if crm_call else None) or lead_data.get("id")
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
             "occurred_at": self._utc(event.occurred_at).isoformat(), "speaker": event.payload_json["speaker"],
             "text": event.payload_json["text"]}
            for event in sorted(events, key=lambda item: (item.sequence is None, item.sequence or 0,
                                                           item.occurred_at, item.event_id))
            if event.event_type == "voice.transcript.final"
            and event.payload_json.get("speaker") in {"user", "assistant"}
            and isinstance(event.payload_json.get("text"), str)
            and event.payload_json["text"].strip()
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
    def _first(events: list[VoiceSessionEvent], *types: str) -> datetime | None:
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
