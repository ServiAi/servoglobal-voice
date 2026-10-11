"""What Telephony needs from other modules and from its SIP transport.
``app.modules.telephony.wiring`` binds these; tests can pass plain fakes.

Every cross-module value is a frozen DTO from the owner's public API (or a
structural Protocol of one) -- never an ORM row.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.modules.telephony.domain.views import LiveKitSipDialResult
from app.modules.voice.public import TelephonySessionView


class VoiceTelephonyPort(Protocol):
    """Session commands, by id. Implemented by voice.public.VoiceTelephonyFacade.
    Voice owns the session, its lifecycle and the runtime/room."""

    def get_session(self, session_id: str, tenant_id: str, *, refresh: bool = False) -> TelephonySessionView: ...

    def lock_session(self, session_id: str, tenant_id: str) -> TelephonySessionView: ...

    def count_active_telephony_sessions(
        self,
        tenant_id: str,
        route_id: str,
        *,
        exclude_session_id: str | None = None,
        exclude_crm_call_id: str | None = None,
    ) -> int: ...

    def create_outbound_sip_session(
        self,
        tenant_id: str,
        agent_id: str,
        *,
        idempotency_key: str,
        contact_id: str | None,
        lead_id: str | None,
        caller_phone: str,
    ) -> TelephonySessionView: ...

    def create_outbound_sip_session_from_agent_version(
        self,
        tenant_id: str,
        agent_id: str,
        agent_version_id: str,
        *,
        idempotency_key: str,
        contact_id: str | None,
        lead_id: str | None,
        caller_phone: str,
        variables: Mapping[str, object] | None = None,
    ) -> TelephonySessionView: ...

    def correlate_crm_call(self, session_id: str, tenant_id: str, crm_voice_call_id: str) -> None: ...

    def cancel_session(self, session_id: str, tenant_id: str, *, end_reason: str) -> None: ...

    def bind_sip_route(
        self, session_id: str, tenant_id: str, *, route_id: str, livekit_trunk_id: str | None
    ) -> None: ...

    async def dispatch_runtime(self, session_id: str, tenant_id: str) -> TelephonySessionView: ...

    def begin_sip_dial(
        self, session_id: str, tenant_id: str, *, route_id: str, participant_identity: str
    ) -> None: ...

    def complete_sip_dial(
        self, session_id: str, tenant_id: str, *, sip_call_id: str, participant_identity: str
    ) -> TelephonySessionView: ...

    def fail_session(
        self,
        session_id: str,
        tenant_id: str,
        *,
        code: str,
        sip_status_event: str | None = None,
        skip_if_terminal: bool = False,
    ) -> None: ...

    async def close_runtime_room(self, session_id: str, tenant_id: str) -> None: ...


class SipTransportPort(Protocol):
    """The LiveKit SIP transport (infrastructure/livekit_sip.LiveKitSipService
    satisfies it). ``dial`` raises LiveKitSipDialError."""

    async def dial(
        self,
        *,
        trunk_id: str,
        to_phone: str,
        from_number: str,
        room_name: str,
        participant_identity: str,
    ) -> LiveKitSipDialResult: ...

    async def provision_outbound_trunk(
        self,
        *,
        trunk_id: str | None,
        name: str,
        address: str,
        number: str,
        username: str,
        password: str,
    ): ...

    async def delete_outbound_trunk(self, trunk_id: str) -> None: ...


class CallLoadPort(Protocol):
    """Channel load held by CRM call records (legacy provider callbacks).
    Implemented by crm.public.CrmFacade."""

    def count_voice_calls_in_statuses(
        self,
        tenant_id: str,
        route_id: str,
        statuses: Sequence[str],
        *,
        exclude_call_id: str | None = None,
        exclude_provider: str | None = None,
    ) -> int: ...


class CallProjectionPort(Protocol):
    """Call-history/CRM projection of a session. Implemented by
    analytics.public.VoiceCallProjectionFacade."""

    def project_session(self, session_id: str, tenant_id: str, *, commit: bool = True) -> None: ...


class OutboundTarget(Protocol):
    @property
    def contact_id(self) -> str: ...
    @property
    def lead_id(self) -> str: ...
    @property
    def phone(self) -> str | None: ...


class LedgerCallState(Protocol):
    @property
    def status(self) -> str: ...
    @property
    def provider_call_id(self) -> str | None: ...


class OutboundCallLedger(Protocol):
    """The caller's record of one outbound call (CRM implements it with
    crm.public.OutboundCallLedger). Telephony never sees the lead/contact/
    call rows; it only drives these steps in this order."""

    def resolve_target(self) -> OutboundTarget:
        """Raises ValueError when the lead/contact is not usable."""
        ...

    def existing_call_id(self) -> str | None:
        """The call record this ledger already owns, to be driven instead of opening a new one
        (a request that was accepted earlier, e.g. a public callback). None otherwise."""
        ...

    def call_state(self, call_id: str) -> LedgerCallState:
        """State of a call opened earlier (idempotent replay). Raises
        ValueError when it is invalid for the tenant."""
        ...

    def open_call(self, *, sip_route_id: str, agent_version_id: str | None, to_phone: str, from_number: str) -> str:
        """Records a requested call (flush, no commit); returns its id."""
        ...

    def mark_dialing(self, call_id: str) -> None:
        """Commits."""
        ...

    def revert_dialing(self, call_id: str) -> None:
        """No SIP attempt was made after ``mark_dialing``: put the call back to ``requested`` so the
        same request can be retried (clears the attempt timestamps and error). Commits."""
        ...

    def mark_answered(self, call_id: str, provider_call_id: str | None) -> None:
        """No commit."""
        ...

    def mark_failed(self, call_id: str, call_status: str, error_code: str) -> None:
        """No commit."""
        ...


@dataclass(frozen=True)
class TelephonyPorts:
    voice: VoiceTelephonyPort
    sip: SipTransportPort
    call_load: CallLoadPort
    projection: CallProjectionPort
