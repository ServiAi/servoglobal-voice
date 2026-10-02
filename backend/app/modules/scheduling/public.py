"""Scheduling -- public API.

Boundary only: implementation still lives in legacy app.modules.scheduling.application.booking_service
(imported lazily: its import graph pulls in Cal.com, Google and notifications).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class BookingSummary:
    id: str
    status: str
    start_at: datetime


class SchedulingFacade:
    def __init__(self, db: Session) -> None:
        self.db = db

    def is_booking_configured(self, tenant_id: str) -> bool:
        """Same resolution the booking tools use at call time."""
        from app.modules.scheduling.application.booking_service import BookingService

        try:
            BookingService(self.db)._effective_config(tenant_id)
            return True
        except ValueError:
            return False

    def get_available_slots(self, *, tenant_id: str, date_input: str) -> dict[str, Any]:
        """Raises ValueError on invalid dates or provider errors."""
        from app.modules.scheduling.application.booking_service import BookingService

        return BookingService(self.db).get_available_slots_for_tenant(tenant_id=tenant_id, date_input=date_input)

    def create_lead_booking(
        self,
        *,
        tenant_id: str,
        lead_id: str,
        start: str,
        attendee_name: str,
        attendee_email: str,
        attendee_phone: str | None,
        notes: Any,
    ) -> BookingSummary:
        """Raises pydantic.ValidationError for a malformed request and
        ValueError for business/provider failures."""
        from app.schemas.crm import BookingCreateRequest
        from app.modules.scheduling.application.booking_service import BookingService

        body = BookingCreateRequest(
            start=start,
            attendee_name=attendee_name,
            attendee_email=attendee_email,
            attendee_phone=attendee_phone,
            notes=notes,
        )
        booking = BookingService(self.db).create_lead_booking(tenant_id=tenant_id, lead_id=lead_id, body=body)
        return BookingSummary(id=booking.id, status=booking.status, start_at=booking.start_at)
