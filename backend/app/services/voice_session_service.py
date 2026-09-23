from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.agents import TenantAgent, TenantAgentVersion
from app.models.crm import CrmContact, CrmLead
from app.models.voice_sessions import VoiceSession, VoiceSessionEvent
from app.schemas.session_context import CampaignContext, SessionContextV1
from app.services.contact_resolution_service import ContactResolutionService


class VoiceSessionError(ValueError):
    pass


class VoiceSessionNotFoundError(VoiceSessionError):
    pass


class SessionContextEnrichmentError(VoiceSessionError):
    """Base class for a failed controlled-enrichment attempt -- see
    VoiceSessionService.enrich_context(). Always fail-closed: the message
    is a stable code (session_context_*_conflict), never a generic string,
    so a caller can diagnose which identity actually conflicted."""


class SessionContextContactConflictError(SessionContextEnrichmentError):
    pass


class SessionContextLeadConflictError(SessionContextEnrichmentError):
    pass


class SessionContextTenantConflictError(SessionContextEnrichmentError):
    pass


TRANSITIONS = {
    "requested": {"dispatching", "failed", "cancelled"},
    "dispatching": {"dispatched", "failed", "cancelled"},
    "dispatched": {"starting", "ended", "failed", "cancelled"},
    "starting": {"connected", "ended", "failed", "cancelled"},
    "connected": {"ending", "ended", "failed", "cancelled"},
    "ending": {"ended", "failed", "cancelled"},
    "ended": set(),
    "failed": set(),
    "cancelled": set(),
}


class VoiceSessionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        tenant_id: str,
        agent_id: str,
        *,
        channel: str,
        direction: str,
        idempotency_key: str | None = None,
        contact_id: str | None = None,
        lead_id: str | None = None,
        caller_phone: str | None = None,
        variables: dict | None = None,
        purpose: str = "production",
        qa_context_mode: str = "preloaded",
    ) -> VoiceSession:
        if purpose == "qa" and qa_context_mode == "conversation" and (
            contact_id or lead_id or variables or (caller_phone and channel != "sip")
        ):
            raise VoiceSessionError("qa_conversation_context_must_be_empty")
        if idempotency_key:
            existing = self.db.scalar(select(VoiceSession).where(VoiceSession.tenant_id == tenant_id, VoiceSession.idempotency_key == idempotency_key))
            if existing:
                return existing
        agent = self.db.scalar(select(TenantAgent).where(TenantAgent.id == agent_id, TenantAgent.tenant_id == tenant_id).with_for_update())
        if agent is None or agent.status != "active" or not agent.published_version_id:
            raise VoiceSessionError("An active agent with a published version is required.")
        version = self.db.scalar(select(TenantAgentVersion).where(TenantAgentVersion.id == agent.published_version_id, TenantAgentVersion.agent_id == agent.id, TenantAgentVersion.tenant_id == tenant_id, TenantAgentVersion.status == "published"))
        if version is None:
            raise VoiceSessionError("The agent's published version is invalid.")
        runtime = version.runtime_binding_json
        if runtime.get("pipeline_type") != "realtime" or not isinstance(runtime.get("realtime"), dict):
            raise VoiceSessionError("Published agent is not configured for realtime voice.")
        # contact_id/lead_id/caller_phone are only ever trusted here: this
        # is the request-scoped, WRITE_ROLES-authenticated caller of
        # POST /api/v1/voice/sessions (the WebRTC test-call flow), never a
        # bare pass-through of unauthenticated/LLM-supplied input. See
        # ContactResolutionService for the precedence/isolation rules.
        context = ContactResolutionService(self.db).resolve(
            tenant_id=tenant_id,
            phone=caller_phone,
            contact_id=contact_id,
            lead_id=lead_id,
            trusted_ids=True,
            source=(
                "webrtc"
                if channel == "webrtc"
                else "outbound"
                if channel == "sip" and direction == "outbound"
                else "manual"
            ),
            variables=variables,
        )
        session = VoiceSession(
            tenant_id=tenant_id, agent_id=agent.id, agent_version_id=version.id, channel=channel, direction=direction,
            purpose=purpose,
            runtime_engine="livekit", pipeline_type="realtime", provider=runtime["realtime"].get("provider", ""),
            idempotency_key=idempotency_key, session_context_json=context.model_dump(mode="json"),
        )
        self.db.add(session)
        self.db.flush()
        self._record_context_events(session, context)
        self.record_event(session, "voice.session.requested", source="control-plane", commit=False)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            if not idempotency_key:
                raise
            existing = self.db.scalar(select(VoiceSession).where(VoiceSession.tenant_id == tenant_id, VoiceSession.idempotency_key == idempotency_key))
            if existing is None:
                raise
            return existing
        self.db.refresh(session)
        return session

    def _record_context_events(self, session: VoiceSession, context: SessionContextV1) -> None:
        # Structured, PII-free observability for context resolution: only
        # booleans and the session/tenant ids, never a name/phone/email --
        # same discipline as ToolDispatchService's own audit events. Always
        # emits "resolved" (the resolution step ran, whatever the outcome);
        # additionally emits "contact_matched"/"lead_matched" only when
        # something was actually found, and "unresolved" when no Contact
        # could be matched at all (the caller may still be known -- see
        # `caller_known` on the "resolved" payload for that).
        contact_resolved = context.contact is not None
        lead_resolved = context.lead is not None
        campaign_resolved = context.campaign is not None
        self.record_event(
            session, "session.context.resolved", source="control-plane",
            payload={
                "contact_resolved": contact_resolved,
                "lead_resolved": lead_resolved,
                "campaign_resolved": campaign_resolved,
                "caller_known": context.caller is not None,
            },
            commit=False,
        )
        if contact_resolved:
            self.record_event(session, "session.context.contact_matched", source="control-plane", commit=False)
        if lead_resolved:
            self.record_event(session, "session.context.lead_matched", source="control-plane", commit=False)
        if not contact_resolved:
            self.record_event(session, "session.context.unresolved", source="control-plane", commit=False)

    def enrich_context(
        self,
        session: VoiceSession,
        *,
        contact: CrmContact | None = None,
        lead: CrmLead | None = None,
        event_source: str | None = None,
        commit: bool = True,
    ) -> SessionContextV1:
        """Controlled monotonic enrichment of an already-created session's
        context: unresolved -> resolved, or unchanged -- never replaces an
        already-resolved contact/lead with a different one (fails closed
        instead), and never touches `caller`/`variables`/`source` at all.
        This is NOT a general-purpose mutation API; it exists specifically
        so a tool that resolves identity mid-conversation (e.g.
        crm.create_lead) can make that identity available to a later tool
        call in the same session (e.g. calendar.create_booking) without
        the LLM ever supplying contact_id/lead_id itself.

        `contact`/`lead` are real ORM rows (not bare ids) so their own
        `tenant_id` can be checked directly against `session.tenant_id` --
        the same "never trust a bare id" discipline as
        ContactResolutionService. A `lead` must belong to the contact
        being enriched (either the one just passed, or the one already on
        the session), otherwise it's a contact/lead conflict, not a lead
        conflict specifically.
        """
        current = SessionContextV1.model_validate(session.session_context_json or {})

        new_contact = current.contact
        if contact is not None:
            if contact.tenant_id != session.tenant_id:
                raise SessionContextTenantConflictError("session_context_tenant_conflict")
            if current.contact is None:
                new_contact = ContactResolutionService.to_contact_context(contact)
            elif current.contact.id != contact.id:
                raise SessionContextContactConflictError("session_context_contact_conflict")
            # else: same contact as already resolved -- idempotent, keep
            # the existing stored representation rather than silently
            # refreshing name/email/phone from a possibly-newer row.

        new_lead = current.lead
        new_campaign = current.campaign
        if lead is not None:
            if lead.tenant_id != session.tenant_id:
                raise SessionContextTenantConflictError("session_context_tenant_conflict")
            expected_contact_id = contact.id if contact is not None else (current.contact.id if current.contact else None)
            if expected_contact_id is not None and lead.contact_id != expected_contact_id:
                raise SessionContextContactConflictError("session_context_contact_conflict")
            if current.lead is None:
                new_lead = ContactResolutionService.to_lead_context(lead)
            elif current.lead.id != lead.id:
                raise SessionContextLeadConflictError("session_context_lead_conflict")
            if new_campaign is None and lead.campaign:
                new_campaign = CampaignContext(name=lead.campaign)

        enriched = SessionContextV1(
            schema_version=current.schema_version,
            source=current.source,
            caller=current.caller,
            contact=new_contact,
            lead=new_lead,
            campaign=new_campaign,
            variables=current.variables,
        )
        session.session_context_json = enriched.model_dump(mode="json")
        # PII-free by construction: only booleans and the triggering
        # tool/source name, same discipline as _record_context_events.
        self.record_event(
            session, "session.context.enriched", source="control-plane",
            payload={
                "contact_resolved": enriched.contact is not None,
                "lead_resolved": enriched.lead is not None,
                "source": event_source,
            },
            commit=False,
        )
        if commit:
            self.db.commit()
            self.db.refresh(session)
        return enriched

    def get(self, session_id: str, tenant_id: str | None = None) -> VoiceSession:
        query = select(VoiceSession).where(VoiceSession.id == session_id)
        if tenant_id is not None:
            query = query.where(VoiceSession.tenant_id == tenant_id)
        session = self.db.scalar(query)
        if session is None:
            raise VoiceSessionNotFoundError("Voice session not found.")
        return session

    def transition(self, session: VoiceSession, target: str, *, commit: bool = True) -> VoiceSession:
        if target == session.status:
            return session
        if target not in TRANSITIONS.get(session.status, set()):
            raise VoiceSessionError(f"Invalid voice session transition: {session.status} -> {target}")
        session.status = target
        now = datetime.now(timezone.utc)
        if target == "dispatched": session.dispatched_at = now
        elif target == "starting": session.started_at = now
        elif target == "connected": session.connected_at = now
        elif target in {"ended", "failed", "cancelled"}: session.ended_at = now
        if commit:
            self.db.commit()
            self.db.refresh(session)
        return session

    def record_event(self, session: VoiceSession, event_type: str, *, source: str, event_id: str | None = None, sequence: int | None = None, payload: dict | None = None, occurred_at: datetime | None = None, commit: bool = True) -> tuple[VoiceSessionEvent, bool]:
        if event_id:
            existing = self.db.scalar(select(VoiceSessionEvent).where(VoiceSessionEvent.event_id == event_id))
            if existing:
                if existing.voice_session_id != session.id:
                    raise VoiceSessionError("Event id belongs to another session.")
                return existing, True
        event = VoiceSessionEvent(event_id=event_id, tenant_id=session.tenant_id, voice_session_id=session.id, event_type=event_type, source=source, sequence=sequence, payload_json=payload or {}, occurred_at=occurred_at or datetime.now(timezone.utc))
        self.db.add(event)
        if commit:
            self.db.commit()
            self.db.refresh(event)
        return event, False

    def fail(self, session: VoiceSession, code: str, message: str) -> VoiceSession:
        session.error_code = code[:80]
        session.error_message_sanitized = message[:500]
        if session.status not in {"failed", "ended", "cancelled"}:
            self.transition(session, "failed", commit=False)
        self.record_event(session, "voice.session.failed", source="control-plane", payload={"error_code": session.error_code}, commit=False)
        self.db.commit()
        return session

    def end(self, session: VoiceSession, reason: str) -> VoiceSession:
        session.end_reason = reason[:40]
        if session.status == "connected": self.transition(session, "ending", commit=False)
        self.transition(session, "ended", commit=False)
        self.record_event(session, "voice.session.ended", source="control-plane", payload={"end_reason": session.end_reason}, commit=False)
        self.db.commit()
        return session
