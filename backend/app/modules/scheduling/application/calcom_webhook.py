"""Reconcile a native Cal.com webhook with the local booking.

The booking lifecycle is Scheduling's, so the webhook only *asks* Scheduling
to apply the change (the HTTP endpoint merely authenticates and parses).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.scheduling.application.ports import SchedulingPorts
from app.modules.scheduling.application.views import booking_view
from app.modules.scheduling.domain.contracts import BookingView
from app.modules.scheduling.infrastructure.models import CrmBooking, CrmBookingEvent

CALCOM_TRIGGER_TO_BOOKING_EVENT = {
    "BOOKING_CREATED": "booking.created",
    "BOOKING_CANCELLED": "booking.cancelled",
    "BOOKING_RESCHEDULED": "booking.rescheduled",
}


def calcom_webhook_status(trigger_event: str | None, payload: dict[str, Any]) -> str:
    status_value = payload.get("status")
    if status_value:
        return str(status_value).lower()
    return {
        "BOOKING_CREATED": "accepted",
        "BOOKING_CANCELLED": "cancelled",
        "BOOKING_RESCHEDULED": "rescheduled",
    }.get(trigger_event or "", "updated")


def safe_webhook_metadata(payload: dict[str, Any]) -> dict[str, str]:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    return {
        "crm_booking_id": str(metadata.get("crm_booking_id") or ""),
        "crm_lead_id": str(metadata.get("crm_lead_id") or ""),
        "source": str(metadata.get("source") or ""),
    }


def reconcile_calcom_webhook(
    db: Session,
    trigger_event: str | None,
    payload: dict[str, Any],
    ports: SchedulingPorts | None = None,
) -> BookingView | None:
    """Apply the webhook to the matching local booking. ``None`` when the
    webhook is not ours or does not match a booking we created."""
    metadata = safe_webhook_metadata(payload)
    if metadata.get("source") != "serviglobal_crm":
        return None

    crm_booking_id = metadata.get("crm_booking_id")
    if not crm_booking_id:
        return None

    booking = db.scalar(
        select(CrmBooking).where(
            CrmBooking.id == crm_booking_id,
            CrmBooking.provider == "calcom",
        )
    )
    if booking is None:
        return None

    crm_lead_id = metadata.get("crm_lead_id")
    if crm_lead_id and crm_lead_id != (booking.lead_id or ""):
        return None

    incoming_provider_id = str(payload.get("id") or "").strip()
    incoming_provider_uid = str(payload.get("uid") or payload.get("bookingUid") or "").strip()

    if (
        booking.provider_booking_id
        and incoming_provider_id
        and str(booking.provider_booking_id) != incoming_provider_id
    ):
        return None
    if (
        booking.provider_booking_uid
        and incoming_provider_uid
        and str(booking.provider_booking_uid) != incoming_provider_uid
    ):
        return None

    if trigger_event == "BOOKING_CANCELLED":
        booking.status = "cancelled"
    elif trigger_event == "BOOKING_RESCHEDULED":
        start_iso = payload.get("startTime")
        end_iso = payload.get("endTime")
        if start_iso:
            booking.start_at = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        if end_iso:
            booking.end_at = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        booking.status = calcom_webhook_status(trigger_event, payload)
    elif trigger_event == "BOOKING_CREATED":
        booking.status = calcom_webhook_status(trigger_event, payload)

    booking.provider_booking_id = incoming_provider_id or booking.provider_booking_id
    booking.provider_booking_uid = incoming_provider_uid or booking.provider_booking_uid
    booking.meeting_url = (
        payload.get("meetingUrl") or payload.get("meeting_url") or payload.get("videoCallUrl") or booking.meeting_url
    )

    safe_summary = {
        "trigger_event": trigger_event,
        "provider_booking_id": booking.provider_booking_id,
        "provider_booking_uid": booking.provider_booking_uid,
        "source": metadata.get("source"),
    }
    db.add(
        CrmBookingEvent(
            tenant_id=booking.tenant_id,
            booking_id=booking.id,
            provider="calcom",
            event_type=(trigger_event or "calcom_webhook").lower(),
            status=booking.status,
            payload_summary_json=safe_summary,
        )
    )
    db.commit()
    if booking.contact_id:
        if ports is None:
            from app.modules.scheduling.wiring import default_scheduling_ports

            ports = default_scheduling_ports(db)
        ports.activity.record_activity(
            tenant_id=booking.tenant_id,
            lead_id=booking.lead_id,
            contact_id=booking.contact_id,
            activity_type="booking_webhook",
            title="Webhook Cal.com",
            description=f"Cal.com {trigger_event or 'webhook'}",
            payload=safe_summary,
        )
    return booking_view(booking)
