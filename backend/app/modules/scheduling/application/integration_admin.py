"""Tenant-level Cal.com / Google Calendar administration shared by the
integrations UI endpoints and the platform-admin endpoints."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.modules.scheduling.application.booking_config_service import BookingConfigService
from app.modules.scheduling.domain.contracts import BookingConfigRequest, BookingConfigResponse
from app.services.integration_event_service import IntegrationEventService


def configure_calcom(db: Session, tenant_id: str, request: BookingConfigRequest) -> BookingConfigResponse:
    """Upsert the tenant's Cal.com config, audit it, return the safe view."""
    service = BookingConfigService(db)
    config = service.upsert_calcom_config(tenant_id, request)
    IntegrationEventService(db).record_event(
        tenant_id=tenant_id,
        provider="calcom",
        event_type="config_updated",
        status="success",
        resource_type="config",
        resource_id=config.id,
        metadata={"has_secret": bool(config.cal_api_key_encrypted), "calendar_mode": config.calendar_mode},
    )
    return service.get_config_response(tenant_id)


def catalog_status_inputs(db: Session, tenant_id: str) -> dict[str, Any]:
    """Facts the integrations catalog classifies; no secrets, no ORM."""
    from app.modules.scheduling.infrastructure.google.oauth import GoogleCalendarOAuthService

    config = BookingConfigService(db).get_config(tenant_id)
    connections = GoogleCalendarOAuthService(db).list_connections(tenant_id)
    return {
        "calcom": {
            "configured": config is not None,
            "status": config.status if config else None,
            "has_error": bool(config and config.last_error_message),
        },
        "google_calendar": {
            "configured": bool(connections),
            "connected": any(c.status == "connected" for c in connections),
            "has_error": any(bool(c.last_error_message) or c.status in {"error", "failed"} for c in connections),
        },
    }
