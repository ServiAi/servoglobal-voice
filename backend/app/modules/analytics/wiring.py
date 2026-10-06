"""Composition root: the only place Analytics reaches Voice, CRM and Agents (via their public APIs)."""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.orm import Session

from app.modules.agents.public import AgentsFacade
from app.modules.analytics.application.ports import (
    AgentDescription,
    CallActivity,
    ProjectionCrmCall,
    ProjectionEvent,
    ProjectionLead,
    ProjectionSession,
)
from app.modules.analytics.application.projection_service import VoiceCallProjectionService
from app.modules.crm.public import CrmFacade, CrmVoiceCalls, UpdateVoiceCallCommand, VoiceCallView
from app.modules.voice.public import SessionEventFact, SessionProjectionFacts, VoiceSessionFacade


def _event(fact: SessionEventFact) -> ProjectionEvent:
    speaker = fact.payload.get("speaker")
    text = fact.payload.get("text")
    return ProjectionEvent(
        event_id=fact.event_id,
        event_type=fact.event_type,
        sequence=fact.sequence,
        occurred_at=fact.occurred_at,
        speaker=speaker if isinstance(speaker, str) else None,
        text=text if isinstance(text, str) else None,
    )


def _session(facts: SessionProjectionFacts) -> ProjectionSession:
    context = facts.context
    return ProjectionSession(
        id=facts.id,
        tenant_id=facts.tenant_id,
        status=facts.status,
        agent_id=facts.agent_id,
        deleted_agent_id=facts.deleted_agent_id,
        agent_version_id=facts.agent_version_id,
        provider=facts.provider,
        provider_session_id=facts.provider_session_id,
        channel=facts.channel,
        direction=facts.direction,
        crm_voice_call_id=facts.crm_voice_call_id,
        requested_at=facts.requested_at,
        started_at=facts.started_at,
        connected_at=facts.connected_at,
        ended_at=facts.ended_at,
        context_contact_id=context.contact.id if context.contact else None,
        context_lead_id=context.lead.id if context.lead else None,
        livekit_room_name=facts.livekit_room_name,
        livekit_dispatch_id=facts.livekit_dispatch_id,
        livekit_sip_trunk_id=facts.livekit_sip_trunk_id,
        livekit_sip_participant_identity=facts.livekit_sip_participant_identity,
        sip_call_id=facts.sip_call_id,
        events=tuple(_event(event) for event in facts.events),
    )


def _crm_call(call: VoiceCallView) -> ProjectionCrmCall:
    return ProjectionCrmCall(
        id=call.id,
        tenant_id=call.tenant_id,
        status=call.status,
        contact_id=call.contact_id,
        lead_id=call.lead_id,
        provider_session_id=call.provider_session_id,
        summary=call.summary,
        recording_url=call.recording_url,
        started_at=call.started_at,
        provider_attempt_started_at=call.provider_attempt_started_at,
        answered_at=call.answered_at,
        ended_at=call.ended_at,
    )


class VoiceSessionAdapter:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_session(self, session_id: str, tenant_id: str | None, *, lock: bool = True) -> ProjectionSession:
        return _session(VoiceSessionFacade(self.db).get_projection_facts(session_id, tenant_id, lock=lock))


class CrmAdapter:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_call(self, call_id: str) -> ProjectionCrmCall | None:
        call = CrmVoiceCalls(self.db).get(call_id)
        return _crm_call(call) if call is not None else None

    def update_call(self, call_id: str, changes: Mapping[str, object]) -> ProjectionCrmCall:
        return _crm_call(CrmVoiceCalls(self.db).update(call_id, UpdateVoiceCallCommand(**changes)))

    def get_lead(self, tenant_id: str, lead_id: str) -> ProjectionLead | None:
        lead = CrmFacade(self.db).get_lead_profile(tenant_id, lead_id)
        if lead is None:
            return None
        return ProjectionLead(id=lead.id, contact_id=lead.contact_id, last_call_id=lead.last_call_id)

    def contact_exists(self, tenant_id: str, contact_id: str) -> bool:
        return CrmFacade(self.db).get_contact_profile(tenant_id, contact_id) is not None

    def upsert_call_activity(self, activity: CallActivity) -> None:
        CrmFacade(self.db).upsert_call_activity(
            tenant_id=activity.tenant_id,
            call_id=activity.call_id,
            activity_type="voice_call",
            deduplication_key=activity.deduplication_key,
            contact_id=activity.contact_id,
            lead_id=activity.lead_id,
            title=activity.title,
            occurred_at=activity.occurred_at,
            outcome=activity.outcome,
            payload=dict(activity.payload),
        )

    def set_lead_last_call(self, tenant_id: str, lead_id: str, call_id: str) -> None:
        CrmFacade(self.db).set_lead_last_call(tenant_id, lead_id, call_id)


class AgentCatalogAdapter:
    def __init__(self, db: Session) -> None:
        self.db = db

    def describe_agent(self, tenant_id: str, agent_id: str, agent_version_id: str | None) -> AgentDescription:
        display = AgentsFacade(self.db).describe_agent(tenant_id, agent_id, agent_version_id)
        return AgentDescription(name=display.name, status=display.status)


def build_projection_service(db: Session) -> VoiceCallProjectionService:
    return VoiceCallProjectionService(
        db,
        sessions=VoiceSessionAdapter(db),
        crm=CrmAdapter(db),
        agent_catalog=AgentCatalogAdapter(db),
    )
