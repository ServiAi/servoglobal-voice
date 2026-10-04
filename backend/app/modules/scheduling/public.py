"""Scheduling -- public API.

The one door into the booking, availability and agent-scheduling context.
Importing this module only loads contracts and errors; use cases are imported
lazily inside each method. Nothing returned here is an ORM row, a provider
token or a Cal.com key: callers get frozen DTOs / plain JSON.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy.orm import Session

from app.modules.scheduling.domain.contracts import (
    BookingConfigRequest,
    BookingConfigResponse,
    BookingCustomer,
    BookingSummary,
    BookingView,
    CalComTestResponse,
    CreateBookingCommand,
    GoogleCalendarConnectionResponse,
)
from app.modules.scheduling.domain.errors import (
    AvailabilityError,
    BookingCustomerNotFoundError,
    BookingNotFoundError,
    BookingOperationInProgressError,
    IdempotencyConflictError,
    SchedulingConfigurationError,
    SchedulingError,
    SlotConflictError,
)

__all__ = [
    "AvailabilityError",
    "BookingConfigRequest",
    "BookingConfigResponse",
    "BookingCustomer",
    "BookingCustomerNotFoundError",
    "BookingNotFoundError",
    "BookingOperationInProgressError",
    "BookingSummary",
    "BookingView",
    "CalComTestResponse",
    "CreateBookingCommand",
    "GoogleCalendarConnectionResponse",
    "IdempotencyConflictError",
    "SchedulingConfigurationError",
    "SchedulingError",
    "SchedulingFacade",
    "SlotConflictError",
]


class SchedulingFacade:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _bookings(self):
        from app.modules.scheduling.application.booking_service import BookingService

        return BookingService(self.db)

    # -- readiness and availability -----------------------------------------

    def is_booking_configured(self, tenant_id: str) -> bool:
        """Same resolution the booking tools use at call time."""
        return self._bookings().is_booking_configured(tenant_id)

    def get_available_slots(
        self,
        *,
        tenant_id: str,
        date_input: str,
        jornada: str | None = None,
        reference_datetime: str | None = None,
        booking_config_id: str | None = None,
        resource_id: str | None = None,
        team_id: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Raises ValueError on invalid dates or provider errors."""
        return self._bookings().get_available_slots_for_tenant(
            tenant_id=tenant_id,
            date_input=date_input,
            jornada=jornada,
            reference_datetime=reference_datetime,
            booking_config_id=booking_config_id,
            resource_id=resource_id,
            team_id=team_id,
            agent_id=agent_id,
        )

    def find_voice_booking_config_id(self, tenant_id: str, provider_agent_id: str | None) -> str | None:
        """The active voice booking config of a provider agent, as an id."""
        from app.modules.scheduling.application.voice_booking import (
            find_voice_booking_config_id,
        )

        return find_voice_booking_config_id(self.db, tenant_id, provider_agent_id)

    # -- booking lifecycle ---------------------------------------------------

    def create_lead_booking(
        self,
        *,
        tenant_id: str,
        lead_id: str,
        start: str,
        attendee_name: str,
        attendee_email: str,
        attendee_phone: str | None,
        notes: str | None,
        idempotency_key: str | None = None,
    ) -> BookingSummary:
        """Tool Platform flavour. Raises pydantic.ValidationError for a
        malformed request and ValueError for business/provider failures."""
        command = CreateBookingCommand.validated(
            start=start,
            attendee_name=attendee_name,
            attendee_email=attendee_email,
            attendee_phone=attendee_phone,
            notes=notes,
        )
        booking = self._bookings().create_lead_booking(
            tenant_id=tenant_id, lead_id=lead_id, command=command, idempotency_key=idempotency_key
        )
        return BookingSummary(id=booking.id, status=booking.status, start_at=booking.start_at)

    def create_booking(
        self,
        *,
        tenant_id: str,
        lead_id: str,
        command: CreateBookingCommand,
        booking_config_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> BookingView:
        from app.modules.scheduling.application.views import booking_view

        booking = self._bookings().create_lead_booking(
            tenant_id=tenant_id,
            lead_id=lead_id,
            command=command,
            booking_config_id=booking_config_id,
            idempotency_key=idempotency_key,
        )
        return booking_view(booking)

    def list_lead_bookings(self, *, tenant_id: str, lead_id: str) -> list[BookingView]:
        from app.modules.scheduling.application.views import booking_view

        return [booking_view(b) for b in self._bookings().list_lead_bookings(tenant_id=tenant_id, lead_id=lead_id)]

    def get_booking(self, *, tenant_id: str, booking_id: str) -> BookingView:
        from app.modules.scheduling.application.views import booking_view

        return booking_view(self._bookings().get_booking(tenant_id=tenant_id, booking_id=booking_id))

    def cancel_booking(self, *, tenant_id: str, booking_id: str) -> dict[str, Any]:
        return self._bookings().cancel_lead_booking(tenant_id=tenant_id, booking_id=booking_id)

    def reschedule_booking(self, *, tenant_id: str, booking_id: str, new_start_time: str) -> dict[str, Any]:
        return self._bookings().reschedule_lead_booking(
            tenant_id=tenant_id, booking_id=booking_id, new_start_time=new_start_time
        )

    def detach_customers(self, *, tenant_id: str, lead_ids: Sequence[str], contact_ids: Sequence[str]) -> None:
        """CRM deleted these leads/contacts: keep the bookings, clear the
        now-dangling references (no commit; part of the caller's transaction)."""
        from app.modules.scheduling.application.booking_history import detach_customers

        detach_customers(self.db, tenant_id, lead_ids, contact_ids)

    # -- tenant-level administration (platform admin / integrations UI) ------

    def get_booking_config(self, tenant_id: str) -> BookingConfigResponse:
        from app.modules.scheduling.application.booking_config_service import (
            BookingConfigService,
        )

        return BookingConfigService(self.db).get_config_response(tenant_id)

    def configure_calcom(self, tenant_id: str, request: BookingConfigRequest) -> BookingConfigResponse:
        """Raises ValueError (422 upstream) on an invalid configuration."""
        from app.modules.scheduling.application.integration_admin import (
            configure_calcom,
        )

        return configure_calcom(self.db, tenant_id, request)

    def test_calcom(self, tenant_id: str) -> tuple[str, str | None]:
        """(status, error_message). Raises ValueError when not configured."""
        from app.modules.scheduling.application.booking_config_service import (
            BookingConfigService,
        )

        return BookingConfigService(self.db).test_connection(tenant_id)

    def list_google_connections(self, tenant_id: str) -> list[GoogleCalendarConnectionResponse]:
        from app.modules.scheduling.infrastructure.google.oauth import (
            GoogleCalendarOAuthService,
        )

        service = GoogleCalendarOAuthService(self.db)
        return [service.response(c) for c in service.list_connections(tenant_id)]

    def delete_google_connection(self, tenant_id: str, connection_id: str) -> None:
        """Raises ValueError when the connection does not exist."""
        from app.modules.scheduling.infrastructure.google.oauth import (
            GoogleCalendarOAuthService,
        )

        GoogleCalendarOAuthService(self.db).delete_connection(tenant_id, connection_id)

    # -- provider status for the integrations catalog ------------------------

    def catalog_status_inputs(self, tenant_id: str) -> dict[str, Any]:
        """What the integrations catalog needs to classify Cal.com/Google:
        booleans and status strings only."""
        from app.modules.scheduling.application.integration_admin import (
            catalog_status_inputs,
        )

        return catalog_status_inputs(self.db, tenant_id)
