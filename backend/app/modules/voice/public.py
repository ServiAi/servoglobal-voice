"""Voice Orchestration -- public API (control plane of voice sessions).

Top-level imports are limited to pure contracts, views and errors, so other
modules (e.g. Agent Builder's compiler, which produces RuntimeSessionSpecV1)
can import this module without loading sessions, CRM, LiveKit or provider
adapters. Use cases are imported lazily inside the facade.

Nothing returned here is a VoiceSession/VoiceSessionEvent row. Voice
providers have their own boundary (app.modules.voice_providers.public).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.modules.crm.public import ContactRef, LeadRef
from app.modules.voice.domain.errors import (
    ContactResolutionError,
    CrossTenantResolutionError,
    SessionContextContactConflictError,
    SessionContextEnrichmentError,
    SessionContextLeadConflictError,
    SessionContextTenantConflictError,
    VoiceSessionError,
    VoiceSessionNotFoundError,
    VoiceSessionsBusyError,
)
from app.modules.voice.domain.runtime_contracts import RuntimeSessionSpecV1
from app.modules.voice.domain.session_context import (
    CallerContext,
    CampaignContext,
    ContactContext,
    LeadContext,
    SessionContextV1,
)
from app.modules.voice.domain.views import (
    SessionEventFact,
    SessionProjectionFacts,
    TelephonySessionView,
    ToolBindingView,
    ToolSessionView,
)

__all__ = [
    "CallerContext",
    "CampaignContext",
    "ContactContext",
    "ContactResolutionError",
    "CrossTenantResolutionError",
    "LeadContext",
    "RuntimeSessionSpecV1",
    "SessionContextContactConflictError",
    "SessionContextEnrichmentError",
    "SessionContextLeadConflictError",
    "SessionContextTenantConflictError",
    "SessionContextV1",
    "SessionEventFact",
    "SessionProjectionFacts",
    "TelephonySessionView",
    "ToolBindingView",
    "ToolSessionView",
    "VoiceSessionError",
    "VoiceSessionFacade",
    "VoiceSessionNotFoundError",
    "VoiceSessionsBusyError",
    "VoiceTelephonyFacade",
]


from app.modules.voice.domain.views import TranscriptCompleteness, VoiceConversationEvidence, VoiceToolOutcome


class VoiceSessionFacade:
    """VoiceSession operations other modules may perform, addressed by id."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _ops(self):
        from app.modules.voice.application.facade import VoiceSessionOperations

        return VoiceSessionOperations(self.db)

    def get_tool_session(self, session_id: str) -> ToolSessionView:
        """Raises VoiceSessionNotFoundError."""
        return self._ops().get_tool_session(session_id)

    def read_conversation_evidence(self, tenant_id: str, session_id: str) -> "VoiceConversationEvidence":
        return self._ops().read_conversation_evidence(tenant_id, session_id)

    def record_event(self, session_id: str, event_type: str, *, source: str, payload: dict[str, Any]) -> None:
        self._ops().record_event(session_id, event_type, source=source, payload=payload)

    def enrich_context(
        self, session_id: str, *, contact: ContactRef | None, lead: LeadRef | None, event_source: str
    ) -> None:
        """Monotonic only (unresolved -> resolved, same -> no-op, different or
        cross-tenant -> SessionContextEnrichmentError with a stable code)."""
        self._ops().enrich_context(session_id, contact=contact, lead=lead, event_source=event_source)

    async def release_sessions_of_deleted_agent(self, tenant_id: str, agent_id: str) -> None:
        """Closes live rooms, cancels and detaches every session of an agent
        that is being deleted, inside the caller's transaction (no commit).
        Raises VoiceSessionsBusyError (``.code``) when that is not safe."""
        await self._ops().release_sessions_of_deleted_agent(tenant_id, agent_id)

    def get_projection_facts(
        self, session_id: str, tenant_id: str | None = None, *, lock: bool = True
    ) -> SessionProjectionFacts:
        """Locks the session row for the caller's transaction unless
        ``lock=False``. Raises VoiceSessionNotFoundError."""
        return self._ops().get_projection_facts(session_id, tenant_id, lock=lock)

    def list_projection_candidates(
        self, *, after_id: str, limit: int, tenant_id: str | None = None
    ) -> list[tuple[str, str]]:
        """Next page of (session_id, tenant_id) to reconcile, ordered by id."""
        return self._ops().list_projection_candidates(after_id=after_id, limit=limit, tenant_id=tenant_id)

    def agent_ids_by_crm_call(self, tenant_id: str, crm_voice_call_ids: list[str]) -> dict[str, str | None]:
        return self._ops().agent_ids_by_crm_call(tenant_id, crm_voice_call_ids)


class VoiceTelephonyFacade:
    """The session commands Telephony needs to dial a VoiceSession. All
    addressed by id and returning TelephonySessionView snapshots; Voice keeps
    the session row, its lifecycle and the runtime/LiveKit room.

    ``runtime_backend`` is a test seam for the runtime transport (default:
    the real LiveKit backend, created on first use).
    """

    def __init__(self, db: Session, *, runtime_backend: Any = None) -> None:
        self.db = db
        self._runtime_backend = runtime_backend

    def _ops(self):
        from app.modules.voice.application.telephony_ops import (
            TelephonySessionOperations,
        )

        return TelephonySessionOperations(self.db, self._runtime_backend)

    def get_session(self, session_id: str, tenant_id: str, *, refresh: bool = False) -> TelephonySessionView:
        """Raises VoiceSessionNotFoundError."""
        return self._ops().get_session(session_id, tenant_id, refresh=refresh)

    def lock_session(self, session_id: str, tenant_id: str) -> TelephonySessionView:
        """SELECT ... FOR UPDATE on the session row, for the caller's
        transaction. Raises VoiceSessionNotFoundError."""
        return self._ops().lock_session(session_id, tenant_id)

    def count_active_telephony_sessions(
        self, tenant_id: str, route_id: str, *, exclude_session_id: str | None = None
    ) -> int:
        """Non-terminal sessions bound to the route (tenant-scoped)."""
        return self._ops().count_active_telephony_sessions(
            tenant_id, route_id, exclude_session_id=exclude_session_id
        )

    def create_outbound_sip_session(
        self,
        tenant_id: str,
        agent_id: str,
        *,
        idempotency_key: str,
        contact_id: str | None,
        lead_id: str | None,
        caller_phone: str,
    ) -> TelephonySessionView:
        """Idempotent per (tenant, idempotency_key). Raises VoiceSessionError."""
        return self._ops().create_outbound_sip_session(
            tenant_id,
            agent_id,
            idempotency_key=idempotency_key,
            contact_id=contact_id,
            lead_id=lead_id,
            caller_phone=caller_phone,
        )

    def correlate_crm_call(self, session_id: str, tenant_id: str, crm_voice_call_id: str) -> None:
        """Records the caller's opaque call id on the session (flush, no commit)."""
        self._ops().correlate_crm_call(session_id, tenant_id, crm_voice_call_id)

    def cancel_session(self, session_id: str, tenant_id: str, *, end_reason: str) -> None:
        self._ops().cancel_session(session_id, tenant_id, end_reason=end_reason)

    def bind_sip_route(
        self, session_id: str, tenant_id: str, *, route_id: str, livekit_trunk_id: str | None
    ) -> None:
        self._ops().bind_sip_route(session_id, tenant_id, route_id=route_id, livekit_trunk_id=livekit_trunk_id)

    async def dispatch_runtime(self, session_id: str, tenant_id: str) -> TelephonySessionView:
        """Hands the session to the voice runtime (room, job, archival race
        protection stay in Voice). The returned status is ``failed`` when
        the dispatch failed."""
        return await self._ops().dispatch_runtime(session_id, tenant_id)

    def begin_sip_dial(self, session_id: str, tenant_id: str, *, route_id: str, participant_identity: str) -> None:
        self._ops().begin_sip_dial(session_id, tenant_id, route_id=route_id, participant_identity=participant_identity)

    def complete_sip_dial(
        self, session_id: str, tenant_id: str, *, sip_call_id: str, participant_identity: str
    ) -> TelephonySessionView:
        return self._ops().complete_sip_dial(
            session_id, tenant_id, sip_call_id=sip_call_id, participant_identity=participant_identity
        )

    def fail_session(
        self,
        session_id: str,
        tenant_id: str,
        *,
        code: str,
        sip_status_event: str | None = None,
        skip_if_terminal: bool = False,
    ) -> None:
        self._ops().fail_session(
            session_id, tenant_id, code=code, sip_status_event=sip_status_event, skip_if_terminal=skip_if_terminal
        )

    async def close_runtime_room(self, session_id: str, tenant_id: str) -> None:
        """Best effort: a failure is recorded as ``voice.cleanup.failed``."""
        await self._ops().close_runtime_room(session_id, tenant_id)
