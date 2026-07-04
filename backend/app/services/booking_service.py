from __future__ import annotations

from dataclasses import replace
from datetime import UTC, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.crm import CrmBooking, CrmBookingEvent, CrmLead
from app.models.integrations import TenantBookingConfig, TenantVoiceBookingConfig
from app.schemas.crm import BookingCancelRequest, BookingCreateRequest, BookingRescheduleRequest
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
        booking_config_id: str | None = None,
        voice_config: TenantVoiceBookingConfig | None = None,
    ) -> dict:
        config, client_config, _ = self._effective_config(
            tenant_id,
            booking_config_id=booking_config_id,
            voice_config=voice_config,
        )
        result = self.calcom_client.get_available_slots(
            client_config,
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

    def create_lead_booking(
        self,
        *,
        tenant_id: str,
        lead_id: str,
        body: BookingCreateRequest,
        booking_config_id: str | None = None,
        voice_config: TenantVoiceBookingConfig | None = None,
    ) -> CrmBooking:
        lead = self._get_lead(tenant_id, lead_id)
        if not lead.contact.email:
            raise ValueError("Lead contact email is required to create a booking.")
        start_at = parse_utc_start(body.start)
        config, client_config, resolved_voice_config = self._effective_config(
            tenant_id,
            booking_config_id=booking_config_id,
            voice_config=voice_config,
        )
        if config.calendar_mode == "crm_google_insert":
            raise ValueError("Google Calendar insert mode is not enabled yet.")

        event_type_id = body.event_type_id or client_config.event_type_id
        event_type_slug = body.event_type_slug or client_config.event_type_slug
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
            timezone=client_config.timezone if resolved_voice_config else body.timezone or client_config.timezone,
            duration_minutes=config.default_length_minutes,
            attendee_name=body.attendee_name,
            attendee_email=body.attendee_email,
            attendee_phone=body.attendee_phone,
            calendar_mode=config.calendar_mode,
            metadata_json={
                "source": "serviglobal_crm",
                "voice_booking_config_id": resolved_voice_config.id if resolved_voice_config else None,
            },
        )
        self.db.add(booking)
        self.db.commit()
        self.db.refresh(booking)
        self.record_crm_activity(booking, "booking_requested")
        self.record_crm_booking_event(booking, "booking_requested", "pending", {"start_at": body.start})

        payload = self._calcom_payload(
            config=client_config,
            booking=booking,
            body=body,
            event_type_id=event_type_id,
            event_type_slug=event_type_slug,
            username=username,
            team_slug=team_slug,
            organization_slug=organization_slug,
            attendee_timezone=client_config.timezone if resolved_voice_config else None,
        )
        try:
            result = self.calcom_client.create_booking(client_config, payload)
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

    def _effective_config(
        self,
        tenant_id: str,
        *,
        booking_config_id: str | None = None,
        voice_config: TenantVoiceBookingConfig | None = None,
    ) -> tuple[TenantBookingConfig, CalComClientConfig, TenantVoiceBookingConfig | None]:
        resolved_voice_config = voice_config
        if resolved_voice_config is None and booking_config_id:
            resolved_voice_config = self.db.scalar(
                select(TenantVoiceBookingConfig).where(
                    TenantVoiceBookingConfig.id == booking_config_id,
                    TenantVoiceBookingConfig.tenant_id == tenant_id,
                    TenantVoiceBookingConfig.status == "active",
                )
            )

        config = None
        if resolved_voice_config and resolved_voice_config.default_booking_config_id:
            config = self.db.scalar(
                select(TenantBookingConfig).where(
                    TenantBookingConfig.id == resolved_voice_config.default_booking_config_id,
                    TenantBookingConfig.tenant_id == tenant_id,
                    TenantBookingConfig.status.in_(("active", "error")),
                )
            )
            if config is None:
                raise ValueError("Voice booking config points to an inactive Cal.com booking config.")
            if not config.cal_api_key_encrypted:
                raise ValueError("Cal.com API key is not configured for this tenant.")

        config = config or self.config_service.get_active_config(tenant_id)
        client_config = self.config_service.to_client_config(config)
        if resolved_voice_config:
            client_config = replace(
                client_config,
                event_type_id=resolved_voice_config.default_event_type_id or client_config.event_type_id,
                event_type_slug=resolved_voice_config.default_event_type_slug or client_config.event_type_slug,
                timezone=resolved_voice_config.default_timezone or client_config.timezone,
            )
        return config, client_config, resolved_voice_config

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
        attendee_timezone: str | None = None,
    ) -> dict[str, Any]:
        start_at = booking.start_at if booking.start_at.tzinfo else booking.start_at.replace(tzinfo=UTC)
        payload: dict[str, Any] = {
            "start": start_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "attendee": {
                "name": body.attendee_name,
                "email": body.attendee_email,
                "phoneNumber": body.attendee_phone,
                "timeZone": attendee_timezone or body.timezone or config.timezone,
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

    async def cancel_lead_booking(self, tenant_id: str, booking_id: str) -> dict[str, Any]:
        """Cancels a booking via Cal.com and updates the CRM."""
        booking = await self.db.execute(
            select(CRMBooking).where(CRMBooking.id == booking_id, CRMBooking.tenant_id == tenant_id)
        )
        booking = booking.scalar_one_or_none()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")

        client_config = await self.config_service.get_calcom_config(tenant_id)
        client = CalComClient(client_config)

        try:
            await client.cancel_booking(booking.provider_booking_id)
            booking.status = "cancelled"
            
            event = CRMBookingEvent(
                tenant_id=tenant_id,
                booking_id=booking.id,
                event_type="BOOKING_CANCELLED",
                metadata={"reason": "Manual cancellation via CRM"}
            )
            self.db.add(event)
            await self.db.commit()
            return {"status": "success", "booking_id": booking.id}
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to cancel booking: {str(e)}")

    async def reschedule_lead_booking(
        self, tenant_id: str, booking_id: str, new_start_time: datetime, new_end_time: datetime
    ) -> dict[str, Any]:
        """Reschedules a booking via Cal.com and updates the CRM."""
        booking = await self.db.execute(
            select(CRMBooking).where(CRMBooking.id == booking_id, CRMBooking.tenant_id == tenant_id)
        )
        booking = booking.scalar_one_or_none()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")

        client_config = await self.config_service.get_calcom_config(tenant_id)
        client = CalComClient(client_config)

        try:
            await client.reschedule_booking(
                booking.provider_booking_id, 
                new_start_time, 
                new_end_time
            )
            booking.start_time = new_start_time
            booking.end_time = new_end_time
            
            event = CRMBookingEvent(
                tenant_id=tenant_id,
                booking_id=booking.id,
                event_type="BOOKING_RESCHEDULED",
                metadata={
                    "old_start": booking.start_time.isoformat(),
                    "new_start": new_start_time.isoformat()
                }
            )
            self.db.add(event)
            await self.db.commit()
            return {"status": "success", "booking_id": booking.id}
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to reschedule booking: {str(e)}")

    async def reconcile_calcom_webhook(self, tenant_id: str, payload: dict[str, Any]) -> None:
        """Reconciles incoming Cal.com webhooks with CRM state."""
        event_type = payload.get("type")
        data = payload.get("data")
        if not event_type or not data:
            return

        provider_booking_id = data.get("id")
        
        # Find the booking in our CRM
        result = await self.db.execute(
            select(CRMBooking).where(
                CRMBooking.provider_booking_id == provider_booking_id,
                CRMBooking.tenant_id == tenant_id
            )
        )
        booking = result.scalar_one_or_none()

        if not booking:
            return

        if event_type == "BOOKING_CANCELLED":
            booking.status = "cancelled"
        elif event_type == "BOOKING_RESCHEDULED":
            booking.start_time = parse_utc_start(data.get("start"))
            booking.end_time = parse_utc_start(data.get("end"))
            booking.status = "scheduled"

        event = CRMBookingEvent(
            tenant_id=tenant_id,
            booking_id=booking.id,
            event_type=f"CALCOM_{event_type}",
            metadata={"payload": payload}
        )
        self.db.add(event)
        await self.db.commit()

    async def get_booking(self, tenant_id: str, booking_id: str) -> CRMBooking:
        """Retrieves a booking for a specific tenant."""
        result = await self.db.execute(
            select(CRMBooking).where(CRMBooking.id == booking_id, CRMBooking.tenant_id == tenant_id)
        )
        booking = result.scalar_one_or_none()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")
        return booking

    def _safe_provider_summary(self, result: dict[str, Any]) -> dict[str, Any]:
