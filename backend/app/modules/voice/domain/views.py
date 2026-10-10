"""Frozen views Voice hands to other modules -- one per use case, never a
VoiceSession/VoiceSessionEvent row and never a copy of the whole table."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
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


class TranscriptCompleteness(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    NOT_AVAILABLE = "not_available"


@dataclass(frozen=True, slots=True)
class WebRTCJoinInfo:
    """Everything a browser needs to join a session's LiveKit room. The
    participant token is sensitive: hand it to the HTTP response and nowhere else."""

    voice_session_id: str
    server_url: str
    room_name: str
    participant_token: str
    expires_in: int


@dataclass(frozen=True)
class VoiceSessionRef:
    """What other modules get back for a session they asked Voice to create: identifiers and
    the pinned version, never the VoiceSession row."""

    session_id: str
    tenant_id: str
    agent_id: str
    agent_version_id: str
    channel: str
    direction: str
    purpose: str
    status: str
    pipeline_type: str
    provider: str | None


@dataclass(frozen=True)
class TranscriptTurn:
    event_id: str
    sequence: int | None
    speaker: str
    text: str
    occurred_at: datetime


@dataclass(frozen=True)
class VoiceToolOutcome:
    event_id: str
    tool_key: str
    status: str
    duration_ms: int
    error_code: str | None = None


@dataclass(frozen=True)
class VoiceConversationEvidence:
    tenant_id: str
    session_id: str
    purpose: str
    terminal_status: str
    ended_at: datetime | None
    agent_version_id: str | None
    transcript_completeness: TranscriptCompleteness
    turns: tuple[TranscriptTurn, ...]
    tool_outcomes: tuple[VoiceToolOutcome, ...]


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


@dataclass(frozen=True)
class TelephonySessionView:
    """What Telephony may know about a VoiceSession it is dialing. Only the
    fields the dial/outbound flows read; ``crm_voice_call_id`` is an opaque
    correlation id owned by the caller's ledger."""

    id: str
    tenant_id: str
    status: str
    channel: str
    direction: str
    agent_id: str | None
    agent_version_id: str | None
    runtime_ready_at: datetime | None
    livekit_room_name: str | None
    livekit_sip_trunk_id: str | None
    livekit_sip_participant_identity: str | None
    sip_route_id: str | None
    sip_call_id: str | None
    provider_session_id: str | None
    crm_voice_call_id: str | None

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES
