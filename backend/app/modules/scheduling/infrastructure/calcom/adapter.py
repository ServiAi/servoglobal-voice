"""Cal.com booking adapter: executes the provider calls for a booking row."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.modules.scheduling.domain.booking import calcom_booking_fields
from app.modules.scheduling.domain.contracts import (
    BookingCustomer,
    CreateBookingCommand,
)
from app.modules.scheduling.infrastructure.calcom.client import (
    CalComClient,
    CalComClientConfig,
)
from app.modules.scheduling.infrastructure.models import CrmBooking

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
        customer: BookingCustomer,
        command: CreateBookingCommand,
        payload: dict[str, Any],
    ) -> CrmBooking:
        result = self.client.create_booking(self.client_config, payload)
        fields = calcom_booking_fields(result)
        booking.provider_booking_id = fields["provider_booking_id"] or booking.provider_booking_id
        booking.provider_booking_uid = fields["provider_booking_uid"] or booking.provider_booking_uid
        booking.status = fields["status"]
        booking.meeting_url = fields["meeting_url"]
        booking.host_name = fields["host_name"]
        booking.host_email = fields["host_email"]
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
