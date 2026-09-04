from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crm import CrmBooking, CrmLead
from app.models.integrations import TenantBookingConfig, TenantGoogleCalendar, TenantGoogleCalendarConnection
from app.schemas.crm import BookingCreateRequest
from app.services.calcom_client import CalComClient, CalComClientConfig, sanitize_calcom_error
from app.services.google_calendar_service import GoogleCalendarService, sanitize_google_calendar_error
from app.services.scheduling_availability_service import SchedulingAvailabilityService

logger = logging.getLogger(__name__)


class SchedulingProvider(Protocol):
    def get_available_slots(
        self,
        *,
        date_input: str,
        jornada: str | None = None,
        reference_datetime: str | None = None,
    ) -> dict[str, Any]: ...

    def create_booking(
        self,
        *,
        booking: CrmBooking,
        lead: CrmLead,
        body: BookingCreateRequest,
    ) -> CrmBooking: ...

    def cancel_booking(self, *, booking: CrmBooking) -> dict[str, Any]: ...

    def reschedule_booking(self, *, booking: CrmBooking, new_start_at: datetime) -> dict[str, Any]: ...


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


class GoogleCalendarProvider:
    def __init__(
        self,
        db: Session,
        tenant_id: str,
        booking_config: TenantBookingConfig | None = None,
        google_service: GoogleCalendarService | None = None,
        availability_service: SchedulingAvailabilityService | None = None,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.booking_config = booking_config
        self.google_service = google_service or GoogleCalendarService(db)
        self.availability_service = availability_service or SchedulingAvailabilityService(db, self.google_service)

    def _resolve_connection_and_calendar(self) -> tuple[TenantGoogleCalendarConnection, str]:
        connection = self.db.scalar(
            select(TenantGoogleCalendarConnection).where(
                TenantGoogleCalendarConnection.tenant_id == self.tenant_id,
                TenantGoogleCalendarConnection.status == "connected",
            ).order_by(TenantGoogleCalendarConnection.created_at.desc())
        )
        if not connection:
            raise ValueError("No active Google Calendar connection found for this tenant. Google Calendar insert mode is not enabled yet.")

        dest_cal = self.db.scalar(
            select(TenantGoogleCalendar).where(
                TenantGoogleCalendar.tenant_id == self.tenant_id,
                TenantGoogleCalendar.connection_id == connection.id,
                TenantGoogleCalendar.is_booking_destination == True,  # noqa: E712
            )
        )
        calendar_id = dest_cal.google_calendar_id if dest_cal else connection.calendar_id or "primary"
        return connection, calendar_id

    def get_available_slots(
        self,
        *,
        date_input: str,
        jornada: str | None = None,
        reference_datetime: str | None = None,
    ) -> dict[str, Any]:
        tz = self.booking_config.default_timezone if self.booking_config else "America/Bogota"
        duration = self.booking_config.default_length_minutes if self.booking_config else 30
        return self.availability_service.get_available_slots(
            tenant_id=self.tenant_id,
            date_input=date_input,
            jornada=jornada,
            reference_datetime=reference_datetime,
            timezone_str=tz,
            slot_duration_minutes=duration,
        )

    def create_booking(
        self,
        *,
        booking: CrmBooking,
        lead: CrmLead,
        body: BookingCreateRequest,
    ) -> CrmBooking:
        connection, target_cal_id = self._resolve_connection_and_calendar()
        tz = booking.timezone or "America/Bogota"
        duration = booking.duration_minutes or 30
        end_at = booking.end_at or (booking.start_at + timedelta(minutes=duration))

        # Round Robin resource assignment if resources exist
        metadata = dict(booking.metadata_json or {})
        team = metadata.get("team")
        from app.services.scheduling_resource_service import SchedulingResourceService
        res_service = SchedulingResourceService(self.db, self.google_service)
        assigned_resource, assigned_cal_id = res_service.select_resource_round_robin(
            tenant_id=self.tenant_id,
            team=team,
            slot_start=booking.start_at,
            duration_minutes=duration,
        )
        if assigned_resource:
            if assigned_cal_id:
                target_cal_id = assigned_cal_id
            booking.host_name = assigned_resource.name
            booking.host_email = assigned_resource.email
            metadata["scheduling_resource_id"] = assigned_resource.id
            metadata["scheduling_resource_name"] = assigned_resource.name
            if assigned_resource.team:
                metadata["team"] = assigned_resource.team

        summary = booking.title or f"Cita ServiGlobal: {body.attendee_name}"
        host_line = f"\nAsignado a: {booking.host_name}" if booking.host_name else ""
        notes = body.notes or booking.description or "Reserva gestionada por ServiGlobal IA"

        payload = self.google_service.build_event_payload(
            summary=summary,
            description=f"{notes}{host_line}\n\nLead ID: {lead.id}\nTeléfono: {body.attendee_phone or 'N/A'}",
            start_at=booking.start_at,
            end_at=end_at,
            timezone=tz,
            attendee_email=body.attendee_email,
            attendee_name=body.attendee_name,
            enable_meet=True,
        )

        try:
            event = self.google_service.create_event(connection, payload, calendar_id=target_cal_id)
        except Exception as exc:
            message = sanitize_google_calendar_error(str(exc))
            raise ValueError(f"Google Calendar event creation failed: {message}") from exc

        event_id = event.get("id")
        booking.provider = "google_calendar"
        booking.calendar_mode = "crm_google_insert"
        booking.provider_booking_id = event_id
        booking.provider_booking_uid = event_id
        booking.google_calendar_event_id = event_id
        booking.status = "accepted"
        booking.meeting_url = event.get("hangoutLink") or event.get("htmlLink")
        booking.metadata_json = {
            **(booking.metadata_json or {}),
            "google_event": {
                "id": event_id,
                "htmlLink": event.get("htmlLink"),
                "calendar_id": target_cal_id,
            },
        }
        self.db.commit()
        self.db.refresh(booking)
        return booking

    def cancel_booking(self, *, booking: CrmBooking) -> dict[str, Any]:
        connection, target_cal_id = self._resolve_connection_and_calendar()
        event_id = booking.google_calendar_event_id or booking.provider_booking_id
        if event_id:
            try:
                self.google_service.delete_event(connection, event_id, calendar_id=target_cal_id)
            except Exception as exc:
                logger.warning("Google Calendar delete_event error: %s", exc)

        booking.status = "cancelled"
        booking.cancelled_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(booking)
        return {"status": "cancelled", "google_event_id": event_id}

    def reschedule_booking(self, *, booking: CrmBooking, new_start_at: datetime) -> dict[str, Any]:
        connection, target_cal_id = self._resolve_connection_and_calendar()
        event_id = booking.google_calendar_event_id or booking.provider_booking_id
        duration = booking.duration_minutes or 30
        new_end_at = new_start_at + timedelta(minutes=duration)
        tz = booking.timezone or "America/Bogota"

        if event_id:
            patch_payload = {
                "start": {"dateTime": new_start_at.isoformat(), "timeZone": tz},
                "end": {"dateTime": new_end_at.isoformat(), "timeZone": tz},
            }
            try:
                self.google_service.patch_event(connection, event_id, patch_payload, calendar_id=target_cal_id)
            except Exception as exc:
                message = sanitize_google_calendar_error(str(exc))
                raise ValueError(f"Google Calendar event patch failed: {message}") from exc

        booking.start_at = new_start_at
        booking.end_at = new_end_at
        booking.status = "scheduled"
        booking.rescheduled_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(booking)
        return {"status": "rescheduled", "google_event_id": event_id}
