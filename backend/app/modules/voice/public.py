"""Voice Orchestration -- public API.

Boundary only: the implementation still lives in the legacy layers
(app.services.voice_session_service, app.schemas.session_context) until
this module is migrated. Other modules import from here, never from those.
Nothing returned here is an ORM row: VoiceSession, TenantAgent and
TenantAgentVersion stay inside this module.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from sqlalchemy.orm import Session

from app.modules.crm.public import ContactRef, LeadRef
from app.schemas.session_context import SessionContextV1
from app.services import voice_session_service as _sessions
from app.services.voice_session_service import (
    SessionContextEnrichmentError,
    VoiceSessionError,
    VoiceSessionNotFoundError,
)

__all__ = [
    "SessionContextEnrichmentError",
    "SessionContextV1",
    "ToolBindingView",
    "ToolSessionView",
    "VoiceSessionError",
    "VoiceSessionFacade",
    "VoiceSessionNotFoundError",
]

_TERMINAL_STATUSES = frozenset({"ended", "failed", "cancelled"})


@dataclass(frozen=True)
class ToolBindingView:
    """One entry of the published version's ``runtime_binding_json["tools"]``.
    ``config`` is the admin-set binding payload; its schema belongs to Tool
    Platform, so it stays a read-only mapping here."""

    key: str
    enabled: bool
    config: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


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


def _binding_views(runtime_binding_json: Any) -> tuple[ToolBindingView, ...]:
    raw = (runtime_binding_json or {}).get("tools", []) if isinstance(runtime_binding_json, dict) else []
    views = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("key"), str):
            continue
        config = item.get("config")
        views.append(
            ToolBindingView(
                key=item["key"],
                enabled=bool(item.get("enabled", True)),
                config=MappingProxyType(deepcopy(config) if isinstance(config, dict) else {}),
            )
        )
    return tuple(views)


class VoiceSessionFacade:
    """VoiceSession operations other modules may perform, addressed by id."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_tool_session(self, session_id: str) -> ToolSessionView:
        """Raises VoiceSessionNotFoundError."""
        session = _sessions.VoiceSessionService(self.db).get(session_id)
        agent = session.agent
        version = session.agent_version
        return ToolSessionView(
            id=session.id,
            tenant_id=session.tenant_id,
            status=session.status,
            agent_id=session.agent_id,
            agent_status=agent.status if agent is not None else None,
            tool_bindings=_binding_views(version.runtime_binding_json if version is not None else None),
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
