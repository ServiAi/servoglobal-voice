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
from app.modules.voice.domain.errors import VoiceSessionNotFoundError
from app.modules.voice.domain.session_context import SessionContextV1
from app.modules.voice.domain.views import (
    SessionEventFact,
    SessionProjectionFacts,
    ToolSessionView,
)
from app.modules.voice.infrastructure.models import VoiceSession, VoiceSessionEvent


class VoiceSessionOperations:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.sessions = VoiceSessionService(db)

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

    def get_projection_facts(self, session_id: str, tenant_id: str | None) -> SessionProjectionFacts:
        """Locks the session row (SELECT ... FOR UPDATE) for the caller's
        transaction, like the projection always did."""
        query = select(VoiceSession).where(VoiceSession.id == session_id).with_for_update()
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
