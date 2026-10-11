"""Telephony capacity policy: how many channels a tenant's SIP route may
hold, and how the load is read.

Two sources hold a channel on a route and both are kept, exactly as before:

* real VoiceSessions bound to the route (counted by Voice:
  ``count_active_telephony_sessions``), enforced when a session is dialed;
* legacy provider-callback call records (CRM data, counted through
  CallLoadPort by status), enforced when a callback or an outbound request
  is accepted.

Capacity decisions never touch CRM or Voice rows directly.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.telephony.application.ports import CallLoadPort
from app.modules.telephony.domain.capacity import (
    ACTIVE_CALLBACK_STATUSES,
    CANONICAL_SIP_PROVIDER,
    VOICE_CALLBACK_FORCED_RELEASE,
    VOICE_CALLBACK_RECONCILED,
    VOICE_CAPACITY_REACHED,
)
from app.modules.integrations.public import IntegrationEvents


class CapacityService:
    def __init__(self, db: Session, call_load: CallLoadPort) -> None:
        self.db = db
        self.call_load = call_load

    def callbacks_in_flight(self, *, tenant_id: str, route_id: str) -> int:
        return self.call_load.count_voice_calls_in_statuses(tenant_id, route_id, ACTIVE_CALLBACK_STATUSES)

    def route_load(
        self,
        *,
        tenant_id: str,
        route_id: str,
        voice,
        exclude_call_id: str | None = None,
        exclude_session_id: str | None = None,
    ) -> int:
        """Channels held on a route by BOTH runtimes, without counting anything twice: legacy
        provider-callback records (canonical SIP calls are excluded here, their VoiceSession is
        the channel) plus active SIP VoiceSessions. ``exclude_*`` keep a call from counting
        against itself (its record is ``starting`` while it is being placed)."""
        legacy = self.call_load.count_voice_calls_in_statuses(
            tenant_id,
            route_id,
            ACTIVE_CALLBACK_STATUSES,
            exclude_call_id=exclude_call_id,
            exclude_provider=CANONICAL_SIP_PROVIDER,
        )
        sessions = voice.count_active_telephony_sessions(
            tenant_id, route_id, exclude_session_id=exclude_session_id, exclude_crm_call_id=exclude_call_id
        )
        return legacy + sessions

    def record_capacity_reached(
        self,
        *,
        tenant_id: str,
        route_id: str,
        active_calls: int,
        max_concurrent_calls: int,
    ) -> None:
        IntegrationEvents(self.db).record(
            tenant_id=tenant_id,
            provider="telephony",
            event_type=VOICE_CAPACITY_REACHED,
            status="blocked",
            resource_type="sip_route",
            resource_id=route_id,
            metadata={
                "active_calls": active_calls,
                "max_concurrent_calls": max_concurrent_calls,
                "source": "public_callback",
            },
        )

    def record_release(
        self,
        *,
        tenant_id: str,
        call_id: str,
        prior_status: str,
        resulting_status: str,
        forced: bool,
    ) -> None:
        IntegrationEvents(self.db).record(
            tenant_id=tenant_id,
            provider="telephony",
            event_type=(
                VOICE_CALLBACK_FORCED_RELEASE if forced else VOICE_CALLBACK_RECONCILED
            ),
            status="success",
            resource_type="voice_call",
            resource_id=call_id,
            metadata={
                "prior_status": prior_status,
                "resulting_status": resulting_status,
            },
        )
