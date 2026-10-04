"""Pure booking rules: provider selection, payload shaping and status mapping.

No SQLAlchemy, FastAPI, Google, Cal.com client, CRM or Notifications here;
the application layer feeds these functions plain values.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

GOOGLE_PROVIDER = "google_calendar"
CALCOM_PROVIDER = "calcom"
GOOGLE_INSERT_MODE = "crm_google_insert"

BOOKING_EVENT_CREATED = "booking.created"
BOOKING_EVENT_CANCELLED = "booking.cancelled"
BOOKING_EVENT_RESCHEDULED = "booking.rescheduled"

# A booking in one of these states occupies its resource's time. ``failed``,
# ``cancelled`` and ``rejected`` release it. Single source of truth: the slot
# guard and the availability query both use it.
SLOT_BLOCKING_STATUSES = frozenset({"pending", "accepted", "scheduled", "confirmed"})

ACTIVITY_TITLES = {
    "booking_requested": "Reserva solicitada",
    "booking_created": "Reserva creada",
    "booking_failed": "Reserva fallida",
    "voice_booking_requested": "Reserva por voz solicitada",
    "voice_booking_created": "Reserva por voz creada",
    "voice_booking_failed": "Reserva por voz fallida",
}


def is_google_booking(provider: str | None, calendar_mode: str | None) -> bool:
    """A tenant books through Google when configured so, or in CRM-insert mode."""
    return provider == GOOGLE_PROVIDER or calendar_mode == GOOGLE_INSERT_MODE


def booking_is_google(provider: str | None, google_calendar_event_id: str | None) -> bool:
    """An existing booking is cancelled/rescheduled through Google when it was
    created there (or already carries a Google event id)."""
    return provider == GOOGLE_PROVIDER or bool(google_calendar_event_id)


def intervals_overlap(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    """Half-open ``[start, end)``: back-to-back intervals do not overlap."""
    return start_a < end_b and start_b < end_a


def activity_title(activity_type: str) -> str:
    return ACTIVITY_TITLES.get(activity_type, activity_type)


def booking_end(start_at: datetime, duration_minutes: int) -> datetime:
    return start_at + timedelta(minutes=duration_minutes)


def calcom_data(result: Mapping[str, Any]) -> Mapping[str, Any]:
    data = result.get("data")
    return data if isinstance(data, dict) else result


def safe_provider_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    data = calcom_data(result)
    return {
        "provider_booking_id": data.get("id"),
        "provider_booking_uid": data.get("uid") or data.get("bookingUid"),
        "status": data.get("status"),
    }


def calcom_booking_fields(result: Mapping[str, Any]) -> dict[str, Any]:
    """Booking columns derived from a Cal.com response (None = keep current)."""
    data = calcom_data(result)
    return {
        "provider_booking_id": str(data.get("id") or "") or None,
        "provider_booking_uid": str(data.get("uid") or data.get("bookingUid") or "") or None,
        "status": str(data.get("status") or "accepted").lower(),
        "meeting_url": data.get("meetingUrl") or data.get("meeting_url") or data.get("videoCallUrl"),
        "host_name": data.get("hostName") or data.get("host_name"),
        "host_email": data.get("hostEmail") or data.get("host_email"),
    }


def calcom_create_payload(
    *,
    start_at: datetime,
    attendee_name: str,
    attendee_email: str,
    attendee_phone: str | None,
    attendee_timezone: str,
    language: str,
    booking_fields_responses: Mapping[str, Any],
    booking_id: str,
    lead_id: str | None,
    contact_id: str | None,
    event_type_id: int | str | None,
    event_type_slug: str | None,
    username: str | None,
    team_slug: str | None,
    organization_slug: str | None,
) -> dict[str, Any]:
    """The Cal.com ``create booking`` request body (contract with Cal.com)."""
    start = start_at if start_at.tzinfo else start_at.replace(tzinfo=UTC)
    payload: dict[str, Any] = {
        "start": start.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "attendee": {
            "name": attendee_name,
            "email": attendee_email,
            "phoneNumber": attendee_phone,
            "timeZone": attendee_timezone,
            "language": language,
        },
        "bookingFieldsResponses": {
            **booking_fields_responses,
            "crm_lead_id": lead_id,
            "crm_contact_id": contact_id,
            "source": "crm",
        },
        "metadata": {
            "crm_booking_id": booking_id,
            "crm_lead_id": lead_id,
            "crm_contact_id": contact_id,
            "source": "serviglobal_crm",
        },
    }
    if event_type_id:
        payload["eventTypeId"] = event_type_id
    if event_type_slug:
        payload["eventTypeSlug"] = event_type_slug
    if username:
        payload["username"] = username
    if team_slug:
        payload["teamSlug"] = team_slug
    if organization_slug:
        payload["organizationSlug"] = organization_slug
        payload["metadata"]["tenant_slug"] = organization_slug
    return payload
