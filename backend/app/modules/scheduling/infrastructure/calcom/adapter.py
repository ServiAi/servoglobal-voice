"""Cal.com booking adapter: executes the provider calls for a booking row."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.crm import CrmLead
from app.modules.scheduling.infrastructure.calcom.client import CalComClient, CalComClientConfig
from app.modules.scheduling.infrastructure.models import CrmBooking
from app.schemas.crm import BookingCreateRequest

logger = logging.getLogger(__name__)


class CalComProvider:
    def __init__(self, db: Session, client: CalComClient, client_config: CalComClientConfig) -> None:
        self.db = db
        self.client = client
        self.client_config = client_config

    def get_available_slots(
        self,
        *,
        date_input: str,
        jornada: str | None = None,
        reference_datetime: str | None = None,
    ) -> dict[str, Any]:
        return self.client.get_available_slots(
            self.client_config,
            date_input=date_input,
            jornada=jornada,
            reference_datetime=reference_datetime,
        )

    def create_booking(
        self,
        *,
        booking: CrmBooking,
        lead: CrmLead,
        body: BookingCreateRequest,
        payload: dict[str, Any],
    ) -> CrmBooking:
        result = self.client.create_booking(self.client_config, payload)
        data = result.get("data") if isinstance(result.get("data"), dict) else result
        booking.provider_booking_id = str(data.get("id") or "") or booking.provider_booking_id
        booking.provider_booking_uid = str(data.get("uid") or data.get("bookingUid") or "") or booking.provider_booking_uid
        booking.status = str(data.get("status") or "accepted").lower()
        booking.meeting_url = data.get("meetingUrl") or data.get("meeting_url") or data.get("videoCallUrl")
        booking.host_name = data.get("hostName") or data.get("host_name")
        booking.host_email = data.get("hostEmail") or data.get("host_email")
        self.db.commit()
        self.db.refresh(booking)
        return booking

    def cancel_booking(self, *, booking: CrmBooking) -> dict[str, Any]:
        result = self.client.cancel_booking(self.client_config, booking.provider_booking_uid)
        booking.status = "cancelled"
        booking.cancelled_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(booking)
        return result

    def reschedule_booking(self, *, booking: CrmBooking, new_start_at: datetime) -> dict[str, Any]:
        iso_start = new_start_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
        result = self.client.reschedule_booking(self.client_config, booking.provider_booking_uid, iso_start)
        booking.status = "scheduled"
        booking.rescheduled_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(booking)
        return result
