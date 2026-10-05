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
