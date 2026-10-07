"""Ports through which the voice-call projection reaches other modules.

Analytics owns these neutral shapes; ``analytics.wiring`` adapts Voice, CRM and Agents
(``<module>.public``) to them. Nothing here names a foreign module."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ProjectionEvent:
    event_id: str
    event_type: str
    sequence: int | None
    occurred_at: datetime
    speaker: str | None
    text: str | None


@dataclass(frozen=True)
class ProjectionSession:
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
    context_contact_id: str | None
    context_lead_id: str | None
    livekit_room_name: str | None
    livekit_dispatch_id: str | None
    livekit_sip_trunk_id: str | None
    livekit_sip_participant_identity: str | None
    sip_call_id: str | None
    events: tuple[ProjectionEvent, ...]


@dataclass(frozen=True)
class ProjectionCrmCall:
    id: str
    tenant_id: str
    status: str
    contact_id: str | None
    lead_id: str | None
    provider_session_id: str | None
    summary: str | None
    recording_url: str | None
    started_at: datetime | None
    provider_attempt_started_at: datetime | None
    answered_at: datetime | None
    ended_at: datetime | None


@dataclass(frozen=True)
class ProjectionLead:
    id: str
    contact_id: str
    last_call_id: str | None


@dataclass(frozen=True)
class AgentDescription:
    name: str | None
    status: str | None


@dataclass(frozen=True)
class CallActivity:
    tenant_id: str
    call_id: str
    deduplication_key: str
    contact_id: str
    lead_id: str | None
    title: str
    occurred_at: datetime | None
    outcome: str | None
    payload: Mapping[str, object]


class VoiceSessionProjectionPort(Protocol):
    def get_session(self, session_id: str, tenant_id: str | None, *, lock: bool = True) -> ProjectionSession: ...


class CrmCallProjectionPort(Protocol):
    def get_call(self, call_id: str) -> ProjectionCrmCall | None: ...

    def update_call(self, call_id: str, changes: Mapping[str, object]) -> ProjectionCrmCall:
        """``changes`` keys: status, provider_session_id, duration_seconds, ended_at. No commit."""
        ...

    def get_lead(self, tenant_id: str, lead_id: str) -> ProjectionLead | None: ...

    def contact_exists(self, tenant_id: str, contact_id: str) -> bool: ...

    def upsert_call_activity(self, activity: CallActivity) -> None: ...

    def set_lead_last_call(self, tenant_id: str, lead_id: str, call_id: str) -> None: ...


class AgentCatalogPort(Protocol):
    def describe_agent(self, tenant_id: str, agent_id: str, agent_version_id: str | None) -> AgentDescription: ...
