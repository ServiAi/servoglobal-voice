from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.crm import CrmVoiceCall
from app.models.integrations import TenantIntegrationEvent, TenantSipRoute
from app.services.integration_event_service import IntegrationEventService


ACTIVE_CALLBACK_STATUSES = ("starting", "queued", "ringing", "in_progress")
VOICE_CAPACITY_REACHED = "voice_capacity_reached"
VOICE_CALLBACK_RECONCILED = "voice_callback_reconciled"
VOICE_CALLBACK_FORCED_RELEASE = "voice_callback_forced_release"
CAPACITY_EVENT_TYPES = (
    VOICE_CAPACITY_REACHED,
    VOICE_CALLBACK_RECONCILED,
    VOICE_CALLBACK_FORCED_RELEASE,
)


class VoiceCapacityService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def active_calls(self, *, tenant_id: str, route_id: str) -> int:
        return int(
            self.db.scalar(
                select(func.count(CrmVoiceCall.id)).where(
                    CrmVoiceCall.tenant_id == tenant_id,
                    CrmVoiceCall.sip_route_id == route_id,
                    CrmVoiceCall.status.in_(ACTIVE_CALLBACK_STATUSES),
                )
            )
            or 0
        )

    def record_capacity_reached(
        self,
        *,
        tenant_id: str,
        route_id: str,
        active_calls: int,
        max_concurrent_calls: int,
    ) -> None:
        IntegrationEventService(self.db).record_event(
            tenant_id=tenant_id,
            provider="ultravox",
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
        IntegrationEventService(self.db).record_event(
            tenant_id=tenant_id,
            provider="ultravox",
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

    def dashboard_snapshot(
        self,
        *,
        tenant_id: str,
        date_from: datetime,
        date_to: datetime,
    ) -> dict:
        route = self.db.scalar(
            select(TenantSipRoute).where(TenantSipRoute.tenant_id == tenant_id)
        )
        if route is None:
            return self._empty_snapshot()

        active_calls = self.active_calls(tenant_id=tenant_id, route_id=route.id)
        limit = route.max_concurrent_calls
        event_filters = (
            TenantIntegrationEvent.tenant_id == tenant_id,
            TenantIntegrationEvent.provider == "ultravox",
            TenantIntegrationEvent.event_type.in_(CAPACITY_EVENT_TYPES),
            TenantIntegrationEvent.created_at >= date_from,
            TenantIntegrationEvent.created_at <= date_to,
        )
        counts = dict(
            self.db.execute(
                select(TenantIntegrationEvent.event_type, func.count())
                .where(*event_filters)
                .group_by(TenantIntegrationEvent.event_type)
            ).all()
        )
        events = self.db.scalars(
            select(TenantIntegrationEvent)
            .where(*event_filters)
            .order_by(TenantIntegrationEvent.created_at.desc())
            .limit(10)
        ).all()

        event_labels = {
            VOICE_CAPACITY_REACHED: "capacity_reached",
            VOICE_CALLBACK_RECONCILED: "reconciled",
            VOICE_CALLBACK_FORCED_RELEASE: "forced_release",
        }
        recent_events = []
        for event in events:
            metadata = event.metadata_json or {}
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
