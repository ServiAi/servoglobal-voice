"""Telephony-capacity block of the CRM dashboard (reporting only).

Legacy reporting adapter: it composes Telephony's public API (the tenant's
route, the channel load) with the shared integration-event audit table. The
capacity *policy* and its enforcement live in app.modules.telephony; this
moves to the dashboard/analytics module when that one is migrated.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.integrations.public import IntegrationEvents
from app.modules.telephony.public import (
    CAPACITY_EVENT_TYPES,
    VOICE_CALLBACK_FORCED_RELEASE,
    VOICE_CALLBACK_RECONCILED,
    VOICE_CAPACITY_REACHED,
    CapacityFacade,
    SipRouteFacade,
)


class VoiceCapacityReportService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def dashboard_snapshot(
        self,
        *,
        tenant_id: str,
        date_from: datetime,
        date_to: datetime,
    ) -> dict:
        route = SipRouteFacade(self.db).get_route(tenant_id)
        if route is None:
            return self._empty_snapshot()

        active_calls = CapacityFacade(self.db).callbacks_in_flight(tenant_id=tenant_id, route_id=route.id)
        limit = route.max_concurrent_calls
        summary = IntegrationEvents(self.db).summarize(
            tenant_id=tenant_id,
            providers=("telephony", "ultravox"),
            event_types=CAPACITY_EVENT_TYPES,
            date_from=date_from,
            date_to=date_to,
            recent_limit=10,
        )
        counts = summary.counts
        events = summary.recent

        event_labels = {
            VOICE_CAPACITY_REACHED: "capacity_reached",
            VOICE_CALLBACK_RECONCILED: "reconciled",
            VOICE_CALLBACK_FORCED_RELEASE: "forced_release",
        }
        recent_events = []
        for event in events:
            metadata = event.metadata
            recent_events.append(
                {
                    "event_type": event_labels[event.event_type],
                    "occurred_at": event.created_at,
                    "active_calls": metadata.get("active_calls"),
                    "max_concurrent_calls": metadata.get("max_concurrent_calls"),
                    "resulting_status": metadata.get("resulting_status"),
                }
            )

        return {
            "configured": True,
            "route_status": route.status,
            "provision_status": route.provision_status,
            "active_calls": active_calls,
            "max_concurrent_calls": limit,
            "available_slots": max(0, limit - active_calls),
            "utilization_percent": round((active_calls / limit) * 100, 1),
            "capacity_rejections": counts.get(VOICE_CAPACITY_REACHED, 0),
            "reconciled_calls": counts.get(VOICE_CALLBACK_RECONCILED, 0),
            "forced_releases": counts.get(VOICE_CALLBACK_FORCED_RELEASE, 0),
            "recent_events": recent_events,
        }

    @staticmethod
    def _empty_snapshot() -> dict:
        return {
            "configured": False,
            "route_status": None,
            "provision_status": None,
            "active_calls": 0,
            "max_concurrent_calls": 0,
            "available_slots": 0,
            "utilization_percent": 0.0,
            "capacity_rejections": 0,
            "reconciled_calls": 0,
            "forced_releases": 0,
            "recent_events": [],
        }
