from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.agents.public import AgentsFacade, PublishedAgentUnavailableError
from app.modules.voice.application.context_resolution import ContactResolutionService
from app.modules.voice.application.ports import ContactView, LeadView
from app.modules.voice.domain.errors import (  # noqa: F401 -- historical import path for these names
    SessionContextContactConflictError,
    SessionContextEnrichmentError,
    SessionContextLeadConflictError,
    SessionContextTenantConflictError,
    VoiceSessionError,
    VoiceSessionNotFoundError,
    VoiceSessionsBusyError,
)
from app.modules.voice.domain.lifecycle import TERMINAL_STATUSES, TRANSITIONS
from app.modules.voice.domain.session_context import CampaignContext, SessionContextV1
from app.modules.voice.infrastructure.models import VoiceSession, VoiceSessionEvent


class VoiceSessionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        from app.modules.voice.wiring import evaluation_requests

        self.evaluation_requests = evaluation_requests(db)

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
        try:
            published = AgentsFacade(self.db).lock_published_agent(tenant_id, agent_id)
        except PublishedAgentUnavailableError as exc:
            if exc.code == "published_version_invalid":
                raise VoiceSessionError("The agent's published version is invalid.") from exc
            raise VoiceSessionError("An active agent with a published version is required.") from exc
        if not published.is_realtime:
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
            tenant_id=tenant_id, agent_id=published.agent_id, agent_version_id=published.version_id, channel=channel, direction=direction,
            purpose=purpose,
            runtime_engine="livekit", pipeline_type="realtime", provider=published.realtime_provider,
            idempotency_key=idempotency_key, session_context_json=context.model_dump(mode="json"),
        )
        self.db.add(session)
        try:
            # The unique (tenant_id, idempotency_key) constraint can fire at
            # flush as well as at commit when two requests race.
            self.db.flush()
            self._record_context_events(session, context)
            self.record_event(session, "voice.session.requested", source="control-plane", commit=False)
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
        contact: ContactView | None = None,
        lead: LeadView | None = None,
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

        `contact`/`lead` are CRM snapshots re-read by the owner (never ids
        handed over by a caller) so their own `tenant_id` can be checked
        directly against `session.tenant_id` -- the same "never trust a
        bare id" discipline as ContactResolutionService. A `lead` must belong to the contact
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

    async def release_sessions_of_deleted_agent(self, tenant_id: str, agent_id: str) -> None:
        """Closes live rooms, then cancels and detaches (deleted_agent_id /
        deleted_agent_version_id) every session of an agent being deleted.
        Runs inside the caller's transaction: never commits."""
        from app.modules.voice.infrastructure.livekit_runtime import (
            LiveKitRuntimeBackend,
        )

        sessions = list(self.db.scalars(select(VoiceSession).where(
            VoiceSession.tenant_id == tenant_id, VoiceSession.agent_id == agent_id
        ).with_for_update()).all())
        closer = LiveKitRuntimeBackend()
        for session in sessions:
            if session.status in TERMINAL_STATUSES:
                continue
            if session.status == "dispatching" and not session.livekit_room_name:
                raise VoiceSessionsBusyError("agent_delete_session_dispatching")
            if session.status != "requested":
                if session.runtime_engine != "livekit" or session.livekit_room_name not in (None, f"sg-vs-{session.id}"):
                    raise VoiceSessionsBusyError("agent_delete_session_unverified")
                try:
                    await closer.close_session_room(session.id)
                except Exception as exc:
                    raise VoiceSessionsBusyError("agent_delete_room_close_failed") from exc
                self.db.refresh(session)
        for session in sessions:
            if session.status not in TERMINAL_STATUSES:
                session.end_reason = "agent_deleted"
                self.transition(session, "cancelled", commit=False)
                self.record_event(
                    session, "voice.session.cancelled", source="control-plane",
                    payload={"end_reason": session.end_reason}, commit=False,
                )
            session.deleted_agent_id = session.agent_id
            session.deleted_agent_version_id = session.agent_version_id
            session.agent_id = None
            session.agent_version_id = None

    def enrich_context_by_ids(
        self,
        session: VoiceSession,
        *,
        contact_id: str | None,
        lead_id: str | None,
        event_source: str | None = None,
    ) -> SessionContextV1:
        """enrich_context for callers outside this module, which only hold
        ids: re-loads the rows here (by id only, so a cross-tenant row still
        reaches the tenant check above and fails with
        session_context_tenant_conflict) and applies the exact same
        monotonic rules."""
        from app.modules.voice.wiring import crm_context

        crm = crm_context(self.db)
        contact = crm.get_contact(contact_id) if contact_id else None
        if contact_id and contact is None:
            raise SessionContextContactConflictError("session_context_contact_conflict")
        lead = crm.get_lead(lead_id) if lead_id else None
        if lead_id and lead is None:
            raise SessionContextLeadConflictError("session_context_lead_conflict")
        return self.enrich_context(session, contact=contact, lead=lead, event_source=event_source)

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
        elif target in TERMINAL_STATUSES: session.ended_at = now
        if target in TERMINAL_STATUSES:
            tool_outcomes = tuple(
                {
                    "tool_key": event.payload_json.get("tool_key"),
                    "status": event.payload_json.get("status"),
                    "duration_ms": event.payload_json.get("duration_ms"),
                    "error_code": event.payload_json.get("error_code"),
                }
                for event in session.events
                if event.event_type == "session.context.tool_used"
                and event.payload_json.get("status") in {"success", "error"}
                and isinstance(event.payload_json.get("tool_key"), str)
                and isinstance(event.payload_json.get("duration_ms"), int)
            )
            self.evaluation_requests.request_terminal_session(
                tenant_id=session.tenant_id,
                session_id=session.id,
                purpose=session.purpose,
                status=session.status,
                agent_version_id=session.agent_version_id,
                ended_at=session.ended_at,
                error_code=session.error_code,
                tool_outcomes=tool_outcomes,
            )
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
