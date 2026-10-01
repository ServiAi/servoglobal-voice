"""Voice Orchestration -- public API.

Boundary only: the implementation still lives in the legacy layers
(app.services.voice_session_service, app.schemas.session_context) until
this module is migrated. Other modules import from here, never from those.
Nothing returned here is an ORM row: VoiceSession stays inside this module.
Voice providers (registry, adapters) have their own boundary:
app.modules.voice_providers.public.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.modules.agents.public import AgentsFacade, AgentToolBindingView
from app.modules.crm.public import ContactRef, LeadRef
from app.schemas.session_context import SessionContextV1
from app.services import voice_session_service as _sessions
from app.services.voice_session_service import (
    SessionContextEnrichmentError,
    VoiceSessionError,
    VoiceSessionNotFoundError,
    VoiceSessionsBusyError,
)

__all__ = [
    "SessionContextEnrichmentError",
    "SessionContextV1",
    "ToolBindingView",
    "ToolSessionView",
    "VoiceSessionError",
    "VoiceSessionFacade",
    "VoiceSessionNotFoundError",
    "VoiceSessionsBusyError",
]

_TERMINAL_STATUSES = frozenset({"ended", "failed", "cancelled"})

# Agent Builder owns the parsing of runtime_binding_json["tools"]; Voice
# only forwards the views to Tool Platform under this historical name.
ToolBindingView = AgentToolBindingView


@dataclass(frozen=True)
class ToolSessionView:
    """What a tool invocation may know about a live VoiceSession."""

    id: str
    tenant_id: str
    status: str
    agent_id: str | None
    agent_status: str | None
    tool_bindings: tuple[ToolBindingView, ...]
    context: SessionContextV1

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL_STATUSES or self.agent_id is None or self.agent_status == "archived"

    def binding(self, tool_key: str) -> ToolBindingView | None:
        return next((b for b in self.tool_bindings if b.key == tool_key), None)


class VoiceSessionFacade:
    """VoiceSession operations other modules may perform, addressed by id."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_tool_session(self, session_id: str) -> ToolSessionView:
        """Raises VoiceSessionNotFoundError."""
        session = _sessions.VoiceSessionService(self.db).get(session_id)
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
        service = _sessions.VoiceSessionService(self.db)
        service.record_event(service.get(session_id), event_type, source=source, payload=payload)

    def enrich_context(
        self, session_id: str, *, contact: ContactRef | None, lead: LeadRef | None, event_source: str
    ) -> None:
        """Monotonic only (unresolved -> resolved, same -> no-op, different or
        cross-tenant -> SessionContextEnrichmentError with a stable code)."""
        service = _sessions.VoiceSessionService(self.db)
        service.enrich_context_by_ids(
            service.get(session_id),
            contact_id=contact.id if contact else None,
            lead_id=lead.id if lead else None,
            event_source=event_source,
        )

    async def release_sessions_of_deleted_agent(self, tenant_id: str, agent_id: str) -> None:
        """Closes live rooms, cancels and detaches every session of an agent
        that is being deleted, inside the caller's transaction (no commit).
        Raises VoiceSessionsBusyError (``.code``) when that is not safe."""
        await _sessions.VoiceSessionService(self.db).release_sessions_of_deleted_agent(tenant_id, agent_id)
