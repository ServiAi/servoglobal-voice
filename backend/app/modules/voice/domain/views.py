"""Frozen views Voice hands to other modules -- one per use case, never a
VoiceSession/VoiceSessionEvent row and never a copy of the whole table."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any

from app.modules.agents.public import AgentToolBindingView
from app.modules.voice.domain.lifecycle import TERMINAL_STATUSES
from app.modules.voice.domain.session_context import SessionContextV1

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
        return self.status in TERMINAL_STATUSES or self.agent_id is None or self.agent_status == "archived"

    def binding(self, tool_key: str) -> ToolBindingView | None:
        return next((b for b in self.tool_bindings if b.key == tool_key), None)


@dataclass(frozen=True)
class SessionEventFact:
    event_id: str
    event_type: str
    sequence: int | None
    occurred_at: datetime
    payload: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True)
class SessionProjectionFacts:
    """The stable facts of a session that downstream projections (call
    history, CRM call/activity) are built from. Identifiers of the LiveKit
    room/SIP leg are included only for correlated, PII-free logging."""

    id: str
    tenant_id: str
    status: str
    agent_id: str | None
    deleted_agent_id: str | None
    agent_version_id: str | None
    provider: str | None
    provider_session_id: str | None
    channel: str
    direction: str
    crm_voice_call_id: str | None
    requested_at: datetime | None
    started_at: datetime | None
    connected_at: datetime | None
    ended_at: datetime | None
    context: SessionContextV1
    livekit_room_name: str | None
    livekit_dispatch_id: str | None
    livekit_sip_trunk_id: str | None
    livekit_sip_participant_identity: str | None
    sip_call_id: str | None
    events: tuple[SessionEventFact, ...]
