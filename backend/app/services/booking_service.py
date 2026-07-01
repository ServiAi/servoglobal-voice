from __future__ import annotations

from datetime import UTC, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.crm import CrmBooking, CrmBookingEvent, CrmLead
from app.schemas.crm import BookingCreateRequest
from app.services.booking_config_service import BookingConfigService
from app.services.calcom_client import CalComClient, CalComClientConfig, parse_utc_start, sanitize_calcom_error
from app.services.crm_activity_service import CrmActivityService
from app.services.integration_event_service import IntegrationEventService


class BookingService:
    def __init__(
        self,
        db: Session,
        *,
        config_service: BookingConfigService | None = None,
        calcom_client: CalComClient | None = None,
    ) -> None:
        self.db = db
        self.config_service = config_service or BookingConfigService(db)
        self.calcom_client = calcom_client or CalComClient()

    def get_available_slots_for_tenant(
        self,
        *,
        tenant_id: str,
        date_input: str,
        jornada: str | None = None,
        reference_datetime: str | None = None,
    ) -> dict:
        config = self.config_service.get_active_config(tenant_id)
        result = self.calcom_client.get_available_slots(
            self.config_service.to_client_config(config),
            date_input=date_input,
            jornada=jornada,
            reference_datetime=reference_datetime,
        )
        IntegrationEventService(self.db).record_event(
            tenant_id=tenant_id,
            provider="calcom",
            event_type="availability_lookup",
            status="success",
            metadata={"date": result.get("date"), "jornada": result.get("jornada")},
        )
        return result

    def create_lead_booking(self, *, tenant_id: str, lead_id: str, body: BookingCreateRequest) -> CrmBooking:
        lead = self._get_lead(tenant_id, lead_id)
        if not lead.contact.email:
            raise ValueError("Lead contact email is required to create a booking.")
        start_at = parse_utc_start(body.start)
        config = self.config_service.get_active_config(tenant_id)
        if config.calendar_mode == "crm_google_insert":
            raise ValueError("Google Calendar insert mode is not enabled yet.")

        event_type_id = body.event_type_id or config.default_event_type_id
        event_type_slug = body.event_type_slug or config.default_event_type_slug
        username = body.username or config.default_username
        team_slug = body.team_slug or config.default_team_slug
        organization_slug = body.organization_slug or config.organization_slug
        if not event_type_id and not (event_type_slug and (username or team_slug)):
            raise ValueError("event_type_id or event_type_slug plus username/team_slug is required.")

        booking = CrmBooking(
            tenant_id=tenant_id,
            lead_id=lead.id,
            contact_id=lead.contact_id,
            provider="calcom",
            provider_event_type_id=str(event_type_id) if event_type_id else None,
            provider_event_type_slug=event_type_slug,
            title="Reserva Cal.com",
            description=body.notes,
            status="pending",
            start_at=start_at,
            end_at=start_at + timedelta(minutes=config.default_length_minutes),
            timezone=body.timezone or config.default_timezone,
            duration_minutes=config.default_length_minutes,
            attendee_name=body.attendee_name,
            attendee_email=body.attendee_email,
            attendee_phone=body.attendee_phone,
            calendar_mode=config.calendar_mode,
            metadata_json={"source": "serviglobal_crm"},
        )
        self.db.add(booking)
        self.db.commit()
        self.db.refresh(booking)
        self.record_crm_activity(booking, "booking_requested")
        self.record_crm_booking_event(booking, "booking_requested", "pending", {"start_at": body.start})

        payload = self._calcom_payload(
            config=self.config_service.to_client_config(config),
            booking=booking,
            body=body,
            event_type_id=event_type_id,
            event_type_slug=event_type_slug,
            username=username,
            team_slug=team_slug,
            organization_slug=organization_slug,
        )
        try:
            result = self.calcom_client.create_booking(self.config_service.to_client_config(config), payload)
        except Exception as exc:
            booking.status = "failed"
            self.db.commit()
            message = sanitize_calcom_error(str(exc))
            self.record_crm_activity(booking, "booking_failed", message)
            self.record_crm_booking_event(booking, "booking_failed", "failed", {"error": message})
            IntegrationEventService(self.db).record_event(
                tenant_id=tenant_id,
                provider="calcom",
                event_type="booking_create",
                status="failed",
                resource_type="crm_booking",
                resource_id=booking.id,
                message=message,
            )
            raise

        self.map_calcom_response_to_crm_booking(booking, result)
        self.record_crm_activity(booking, "booking_created")
        self.record_crm_booking_event(booking, "booking_created", booking.status, self._safe_provider_summary(result))
        IntegrationEventService(self.db).record_event(
            tenant_id=tenant_id,
            provider="calcom",
            event_type="booking_create",
            status="success",
            resource_type="crm_booking",
            resource_id=booking.id,
            metadata={"booking_id": booking.id, "provider_booking_uid": booking.provider_booking_uid},
        )
        return booking

    def list_lead_bookings(self, *, tenant_id: str, lead_id: str) -> list[CrmBooking]:
        self._get_lead(tenant_id, lead_id)
        return list(
            self.db.scalars(
                select(CrmBooking)
                .where(CrmBooking.tenant_id == tenant_id, CrmBooking.lead_id == lead_id)
                .order_by(CrmBooking.start_at.desc())
            ).all()
        )

    def record_crm_booking_event(self, booking: CrmBooking, event_type: str, status: str, payload_summary: dict[str, Any]) -> None:
        self.db.add(
            CrmBookingEvent(
                tenant_id=booking.tenant_id,
                booking_id=booking.id,
                provider=booking.provider,
                event_type=event_type,
                status=status,
                payload_summary_json=payload_summary,
            )
        )
        self.db.commit()

    def record_crm_activity(self, booking: CrmBooking, activity_type: str, description: str | None = None) -> None:
        if not booking.contact_id:
            return
        titles = {
            "booking_requested": "Reserva solicitada",
            "booking_created": "Reserva creada",
            "booking_failed": "Reserva fallida",
            "voice_booking_requested": "Reserva por voz solicitada",
            "voice_booking_created": "Reserva por voz creada",
            "voice_booking_failed": "Reserva por voz fallida",
        }
        CrmActivityService(self.db).create_activity(
            tenant_id=booking.tenant_id,
            lead_id=booking.lead_id,
            contact_id=booking.contact_id,
            activity_type=activity_type,
            title=titles.get(activity_type, activity_type),
            description=description,
            payload_json={
                "booking_id": booking.id,
                "provider": booking.provider,
                "start_at": booking.start_at.isoformat(),
                "status": booking.status,
            },
        )

    def map_calcom_response_to_crm_booking(self, booking: CrmBooking, result: dict[str, Any]) -> None:
        data = result.get("data") if isinstance(result.get("data"), dict) else result
        booking.provider_booking_id = str(data.get("id") or "") or booking.provider_booking_id
        booking.provider_booking_uid = str(data.get("uid") or data.get("bookingUid") or "") or booking.provider_booking_uid
        booking.status = str(data.get("status") or "accepted").lower()
        booking.meeting_url = data.get("meetingUrl") or data.get("meeting_url") or data.get("videoCallUrl")
        booking.host_name = data.get("hostName") or data.get("host_name")
        booking.host_email = data.get("hostEmail") or data.get("host_email")
        self.db.commit()
        self.db.refresh(booking)

    def _get_lead(self, tenant_id: str, lead_id: str) -> CrmLead:
        lead = self.db.scalar(
            select(CrmLead)
            .options(joinedload(CrmLead.contact))
            .where(CrmLead.tenant_id == tenant_id, CrmLead.id == lead_id)
        )
        if lead is None:
            raise ValueError("Lead not found")
        return lead

    def _calcom_payload(
        self,
        *,
        config: CalComClientConfig,
        booking: CrmBooking,
        body: BookingCreateRequest,
        event_type_id: int | None,
        event_type_slug: str | None,
        username: str | None,
        team_slug: str | None,
        organization_slug: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "start": booking.start_at.isoformat().replace("+00:00", "Z"),
            "attendee": {
                "name": body.attendee_name,
                "email": body.attendee_email,
                "phoneNumber": body.attendee_phone,
                "timeZone": body.timezone or config.timezone,
                "language": config.language,
            },
            "bookingFieldsResponses": {
                **body.booking_fields_responses,
                "crm_lead_id": booking.lead_id,
                "crm_contact_id": booking.contact_id,
                "source": "crm",
            },
            "metadata": {
                "crm_booking_id": booking.id,
                "crm_lead_id": booking.lead_id,
                "crm_contact_id": booking.contact_id,
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

    def _safe_provider_summary(self, result: dict[str, Any]) -> dict[str, Any]:
        data = result.get("data") if isinstance(result.get("data"), dict) else result
        return {
            "provider_booking_id": data.get("id"),
            "provider_booking_uid": data.get("uid") or data.get("bookingUid"),
            "status": data.get("status"),
        }
