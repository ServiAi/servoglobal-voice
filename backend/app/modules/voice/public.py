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
    "ToolBindingView",
    "ToolSessionView",
    "VoiceSessionError",
    "VoiceSessionFacade",
    "VoiceSessionNotFoundError",
    "VoiceSessionsBusyError",
]


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

    def get_projection_facts(self, session_id: str, tenant_id: str | None = None) -> SessionProjectionFacts:
        """Locks the session row for the caller's transaction. Raises
        VoiceSessionNotFoundError."""
        return self._ops().get_projection_facts(session_id, tenant_id)
