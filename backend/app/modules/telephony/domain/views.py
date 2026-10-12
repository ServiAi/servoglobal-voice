"""Frozen values Telephony exchanges with other modules -- never ORM rows."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class SipRouteView:
    """A tenant's SIP route as other modules may see it. Never carries the
    SIP password (only whether one is configured)."""

    id: str
    tenant_id: str
    provider_config_id: str | None
    status: str
    pbx_host: str
    pbx_port: int
    sip_username: str
    caller_id: str
    default_country: str
    allowed_countries: tuple[str, ...]
    max_concurrent_calls: int
    has_sip_password: bool
    provision_status: str
    desired_revision: int
    applied_revision: int
    provision_error_code: str | None
    provisioned_at: datetime | None
    last_provision_attempt_at: datetime | None
    livekit_outbound_trunk_id: str | None
    livekit_provision_status: str
    livekit_provision_error_code: str | None
    livekit_provisioned_at: datetime | None


@dataclass(frozen=True)
class SipRouteSettings:
    """Command: the settings an admin submits for a tenant's SIP route."""

    status: str
    pbx_host: str
    pbx_port: int
    caller_id: str
    default_country: str
    allowed_countries: tuple[str, ...]
    max_concurrent_calls: int
    sip_password: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class PlaceOutboundCallCommand:
    """``agent_version_id`` present -> a VoiceSession pinned to exactly that version; absent -> the
    agent's current published version (the CRM behavior). ``defer_on_capacity`` makes a full route
    raise CapacityDeferred (retryable) instead of cancelling the call."""

    tenant_id: str
    agent_id: str | None
    idempotency_key: str | None
    to_phone: str | None = None
    agent_version_id: str | None = None
    variables: Mapping[str, object] | None = None
    defer_on_capacity: bool = False


@dataclass(frozen=True)
class OutboundCallResult:
    """Outcome of an outbound call. CRM identifiers stay with the caller's
    ledger (OutboundCallLedger); Telephony only reports telephony/voice facts."""

    voice_session_id: str
    status: str
    sip_call_id: str | None
    provider_call_id: str | None
    provider_session_id: str | None


@dataclass(frozen=True)
class LiveKitSipDialResult:
    participant_id: str
    participant_identity: str
    room_name: str
    sip_call_id: str
