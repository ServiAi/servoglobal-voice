"""Booking lifecycle: create, cancel, reschedule, list and availability lookup.

Scheduling governs the booking. Who the customer is, the CRM timeline and the
announcement of booking facts reach the rest of the platform only through the
ports in ``ports.py`` (bound in ``wiring.py``). Transaction boundaries are the
ones the flow always had: the pending booking is committed *before* the
provider call, so no DB lock is ever held across an external request.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.scheduling.application.booking_config_service import BookingConfigService
from app.modules.scheduling.application.ports import SchedulingPorts
from app.modules.scheduling.domain.booking import (
    BOOKING_EVENT_CANCELLED,
    BOOKING_EVENT_CREATED,
    BOOKING_EVENT_RESCHEDULED,
    CALCOM_PROVIDER,
    GOOGLE_INSERT_MODE,
    GOOGLE_PROVIDER,
    activity_title,
    booking_end,
    booking_is_google,
    calcom_booking_fields,
    calcom_create_payload,
    is_google_booking,
    safe_provider_summary,
)
from app.modules.scheduling.domain.contracts import BookingCustomer, CreateBookingCommand
from app.modules.scheduling.domain.errors import BookingNotFoundError, SchedulingConfigurationError
from app.modules.scheduling.infrastructure.calcom.adapter import CalComProvider
from app.modules.scheduling.infrastructure.calcom.client import (
    CalComClient,
    CalComClientConfig,
    parse_utc_start,
    sanitize_calcom_error,
)
from app.modules.scheduling.infrastructure.google.adapter import GoogleCalendarProvider
from app.modules.scheduling.infrastructure.google.calendar import sanitize_google_calendar_error
from app.modules.scheduling.infrastructure.models import (
    CrmBooking,
    CrmBookingEvent,
    TenantBookingConfig,
    TenantGoogleCalendarConnection,
    TenantSchedulingEventType,
    TenantVoiceBookingConfig,
)
from app.services.integration_event_service import IntegrationEventService

logger = logging.getLogger(__name__)


class BookingService:
    def __init__(
        self,
        db: Session,
        *,
        config_service: BookingConfigService | None = None,
        calcom_client: CalComClient | None = None,
        ports: SchedulingPorts | None = None,
    ) -> None:
        self.db = db
        self.config_service = config_service or BookingConfigService(db)
        self.calcom_client = calcom_client or CalComClient()
        self._ports = ports

    @property
    def ports(self) -> SchedulingPorts:
        if self._ports is None:
            from app.modules.scheduling.wiring import default_scheduling_ports

            self._ports = default_scheduling_ports(self.db)
        return self._ports

    # ------------------------------------------------------------------
    # Announcing facts
    # ------------------------------------------------------------------
    def _publish_booking_event_safely(self, *, tenant_id: str, booking_id: str, event_type: str) -> None:
        try:
            self.ports.events.publish_booking_event(
                tenant_id=tenant_id, booking_id=booking_id, event_type=event_type
            )
        except Exception as exc:  # noqa: BLE001 - announcing a fact must never affect the booking
            logger.error(
                "booking_notification_pipeline_error tenant_id=%s booking_id=%s error_type=%s",
                tenant_id,
                booking_id,
                type(exc).__name__,
            )

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------
    def get_available_slots_for_tenant(
        self,
        *,
        tenant_id: str,
        date_input: str,
        jornada: str | None = None,
        reference_datetime: str | None = None,
        booking_config_id: str | None = None,
        voice_config: TenantVoiceBookingConfig | None = None,
        resource_id: str | None = None,
        team_id: str | None = None,
        agent_id: str | None = None,
    ) -> dict:
        config, client_config, _ = self._effective_config(
            tenant_id,
            booking_config_id=booking_config_id,
            voice_config=voice_config,
        )
        if is_google_booking(config.provider, config.calendar_mode):
            provider = GoogleCalendarProvider(self.db, tenant_id=tenant_id, booking_config=config)
            result = provider.get_available_slots(
                date_input=date_input,
                jornada=jornada,
                reference_datetime=reference_datetime,
                resource_id=resource_id,
                team_id=team_id,
                agent_id=agent_id,
            )
            audited_provider = GOOGLE_PROVIDER
        else:
            provider = CalComProvider(self.db, self.calcom_client, client_config)  # type: ignore[arg-type]
            result = provider.get_available_slots(
                date_input=date_input,
                jornada=jornada,
                reference_datetime=reference_datetime,
            )
            audited_provider = CALCOM_PROVIDER
        IntegrationEventService(self.db).record_event(
            tenant_id=tenant_id,
            provider=audited_provider,
            event_type="availability_lookup",
            status="success",
            metadata={"date": result.get("date"), "jornada": result.get("jornada")},
        )
        return result

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------
    def create_lead_booking(
        self,
        *,
        tenant_id: str,
        lead_id: str,
        command: CreateBookingCommand,
        booking_config_id: str | None = None,
        voice_config: TenantVoiceBookingConfig | None = None,
    ) -> CrmBooking:
        customer = self.ports.customer.get_booking_customer(tenant_id, lead_id)
        if not customer.email:
            raise ValueError("Lead contact email is required to create a booking.")
        start_at = parse_utc_start(command.start)
        config, client_config, resolved_voice_config = self._effective_config(
            tenant_id,
            booking_config_id=booking_config_id,
            voice_config=voice_config,
        )
        voice_config_id = resolved_voice_config.id if resolved_voice_config else None

        if is_google_booking(config.provider, config.calendar_mode):
            return self._create_google_booking(
                tenant_id=tenant_id,
                customer=customer,
                command=command,
                start_at=start_at,
                config=config,
                voice_config_id=voice_config_id,
            )
        return self._create_calcom_booking(
            tenant_id=tenant_id,
            customer=customer,
            command=command,
            start_at=start_at,
            config=config,
            client_config=client_config,  # type: ignore[arg-type]
            voice_config_id=voice_config_id,
        )

    def _create_google_booking(
        self,
        *,
        tenant_id: str,
        customer: BookingCustomer,
        command: CreateBookingCommand,
        start_at: datetime,
        config: TenantBookingConfig,
        voice_config_id: str | None,
    ) -> CrmBooking:
        booking = CrmBooking(
            tenant_id=tenant_id,
            lead_id=customer.lead_id,
            contact_id=customer.contact_id,
            provider=GOOGLE_PROVIDER,
            provider_event_type_id=None,
            provider_event_type_slug=None,
            title="Reserva Google Calendar",
            description=command.notes,
            status="pending",
            start_at=start_at,
            end_at=booking_end(start_at, config.default_length_minutes),
            timezone=command.timezone or config.default_timezone,
            duration_minutes=config.default_length_minutes,
            attendee_name=command.attendee_name,
            attendee_email=command.attendee_email,
            attendee_phone=command.attendee_phone,
            calendar_mode=GOOGLE_INSERT_MODE,
            metadata_json={
                "source": "serviglobal_crm",
                "voice_booking_config_id": voice_config_id,
                "scheduling_resource_id": command.scheduling_resource_id,
                "scheduling_team_id": command.scheduling_team_id,
            },
        )
        self.db.add(booking)
        self.db.commit()
        self.db.refresh(booking)
        self.record_crm_activity(booking, "booking_requested")
        self.record_crm_booking_event(booking, "booking_requested", "pending", {"start_at": command.start})

        google_provider = GoogleCalendarProvider(self.db, tenant_id=tenant_id, booking_config=config)
        try:
            booking = google_provider.create_booking(booking=booking, customer=customer, command=command)
        except Exception as exc:
            self._record_failure(booking, GOOGLE_PROVIDER, sanitize_google_calendar_error(str(exc)))
            raise

        self.record_crm_activity(booking, "booking_created")
        self.record_crm_booking_event(
            booking,
            "booking_created",
            booking.status,
            {"provider_booking_id": booking.provider_booking_id, "status": booking.status},
        )
        IntegrationEventService(self.db).record_event(
            tenant_id=tenant_id,
            provider=GOOGLE_PROVIDER,
            event_type="booking_create",
            status="success",
            resource_type="crm_booking",
            resource_id=booking.id,
            metadata={"booking_id": booking.id, "google_calendar_event_id": booking.google_calendar_event_id},
        )
        self._publish_booking_event_safely(
            tenant_id=tenant_id, booking_id=booking.id, event_type=BOOKING_EVENT_CREATED
        )
        return booking

    def _create_calcom_booking(
        self,
        *,
        tenant_id: str,
        customer: BookingCustomer,
        command: CreateBookingCommand,
        start_at: datetime,
        config: TenantBookingConfig,
        client_config: CalComClientConfig,
        voice_config_id: str | None,
    ) -> CrmBooking:
        event_type_id: int | str | None = command.event_type_id or client_config.event_type_id
        event_type_slug = command.event_type_slug or client_config.event_type_slug
        username = command.username or config.default_username
        team_slug = command.team_slug or config.default_team_slug
        organization_slug = command.organization_slug or config.organization_slug

        if command.event_type_id:
            local_et = self.db.scalar(
                select(TenantSchedulingEventType).where(
                    TenantSchedulingEventType.tenant_id == tenant_id,
                    (TenantSchedulingEventType.id == str(command.event_type_id))
                    | (TenantSchedulingEventType.provider_event_type_id == str(command.event_type_id)),
                )
            )
            if local_et:
                if local_et.provider_event_type_id:
                    event_type_id = (
                        int(local_et.provider_event_type_id)
                        if local_et.provider_event_type_id.isdigit()
                        else local_et.provider_event_type_id
                    )
                event_type_slug = local_et.provider_event_type_slug or local_et.slug or event_type_slug

        if not event_type_id and not (event_type_slug and (username or team_slug)):
            raise ValueError("event_type_id or event_type_slug plus username/team_slug is required.")

        booking = CrmBooking(
            tenant_id=tenant_id,
            lead_id=customer.lead_id,
            contact_id=customer.contact_id,
            provider=CALCOM_PROVIDER,
            provider_event_type_id=str(event_type_id) if event_type_id else None,
            provider_event_type_slug=event_type_slug,
            title="Reserva Cal.com",
            description=command.notes,
            status="pending",
            start_at=start_at,
            end_at=booking_end(start_at, config.default_length_minutes),
            timezone=client_config.timezone if voice_config_id else command.timezone or client_config.timezone,
            duration_minutes=config.default_length_minutes,
            attendee_name=command.attendee_name,
            attendee_email=command.attendee_email,
            attendee_phone=command.attendee_phone,
            calendar_mode=config.calendar_mode,
            metadata_json={
                "source": "serviglobal_crm",
                "voice_booking_config_id": voice_config_id,
            },
        )
        self.db.add(booking)
        self.db.commit()
        self.db.refresh(booking)
        self.record_crm_activity(booking, "booking_requested")
        self.record_crm_booking_event(booking, "booking_requested", "pending", {"start_at": command.start})

        payload = self._calcom_payload(
            config=client_config,
            booking=booking,
            command=command,
            event_type_id=event_type_id,
            event_type_slug=event_type_slug,
            username=username,
            team_slug=team_slug,
            organization_slug=organization_slug,
            attendee_timezone=client_config.timezone if voice_config_id else None,
        )
        try:
            result = self.calcom_client.create_booking(client_config, payload)
        except Exception as exc:
            self._record_failure(booking, CALCOM_PROVIDER, sanitize_calcom_error(str(exc)))
            raise

        self.map_calcom_response_to_crm_booking(booking, result)
        self.record_crm_activity(booking, "booking_created")
        self.record_crm_booking_event(booking, "booking_created", booking.status, safe_provider_summary(result))
        IntegrationEventService(self.db).record_event(
            tenant_id=tenant_id,
            provider=CALCOM_PROVIDER,
            event_type="booking_create",
            status="success",
            resource_type="crm_booking",
            resource_id=booking.id,
            metadata={"booking_id": booking.id, "provider_booking_uid": booking.provider_booking_uid},
        )
        self._publish_booking_event_safely(
            tenant_id=tenant_id, booking_id=booking.id, event_type=BOOKING_EVENT_CREATED
        )
        return booking

    def _record_failure(self, booking: CrmBooking, provider: str, message: str) -> None:
        booking.status = "failed"
        self.db.commit()
        self.record_crm_activity(booking, "booking_failed", message)
        self.record_crm_booking_event(booking, "booking_failed", "failed", {"error": message})
        IntegrationEventService(self.db).record_event(
            tenant_id=booking.tenant_id,
            provider=provider,
            event_type="booking_create",
            status="failed",
            resource_type="crm_booking",
            resource_id=booking.id,
            message=message,
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    def list_lead_bookings(self, *, tenant_id: str, lead_id: str) -> list[CrmBooking]:
        self.ports.customer.get_booking_customer(tenant_id, lead_id)
        return list(
            self.db.scalars(
                select(CrmBooking)
                .where(CrmBooking.tenant_id == tenant_id, CrmBooking.lead_id == lead_id)
                .order_by(CrmBooking.start_at.desc())
            ).all()
        )

    def get_booking(self, *, tenant_id: str, booking_id: str) -> CrmBooking:
        booking = self.db.scalar(
            select(CrmBooking).where(CrmBooking.id == booking_id, CrmBooking.tenant_id == tenant_id)
        )
        if not booking:
            raise BookingNotFoundError()
        return booking

    # ------------------------------------------------------------------
    # Configuration resolution
    # ------------------------------------------------------------------
    def _effective_config(
        self,
        tenant_id: str,
        *,
        booking_config_id: str | None = None,
        voice_config: TenantVoiceBookingConfig | None = None,
    ) -> tuple[TenantBookingConfig, CalComClientConfig | None, TenantVoiceBookingConfig | None]:
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
            if config.provider == CALCOM_PROVIDER and not config.cal_api_key_encrypted:
                raise ValueError("Cal.com API key is not configured for this tenant.")

        if config is None:
            try:
                config = self.config_service.get_active_config(tenant_id)
            except ValueError:
                # Fallback: a tenant with a connected Google Calendar can still book.
                g_conn = self.db.scalar(
                    select(TenantGoogleCalendarConnection).where(
                        TenantGoogleCalendarConnection.tenant_id == tenant_id,
                        TenantGoogleCalendarConnection.status == "connected",
                    )
                )
                if g_conn:
                    config = TenantBookingConfig(
                        tenant_id=tenant_id,
                        provider=GOOGLE_PROVIDER,
                        status="active",
                        calendar_mode=GOOGLE_INSERT_MODE,
                        default_timezone="America/Bogota",
                        default_length_minutes=30,
                    )
                else:
                    raise

        client_config = None
        if config.provider == CALCOM_PROVIDER:
            client_config = self.config_service.to_client_config(config)
            if resolved_voice_config:
                client_config = replace(
                    client_config,
                    event_type_id=resolved_voice_config.default_event_type_id or client_config.event_type_id,
                    event_type_slug=resolved_voice_config.default_event_type_slug or client_config.event_type_slug,
                    timezone=resolved_voice_config.default_timezone or client_config.timezone,
                )
        return config, client_config, resolved_voice_config

    def is_booking_configured(self, tenant_id: str) -> bool:
        """Readiness: the same resolution the booking tools use at call time."""
        try:
            self._effective_config(tenant_id)
            return True
        except ValueError:
            return False

    # ------------------------------------------------------------------
    # Booking history and CRM timeline
    # ------------------------------------------------------------------
    def record_crm_booking_event(
        self, booking: CrmBooking, event_type: str, status: str, payload_summary: dict[str, Any]
    ) -> None:
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
        self.ports.activity.record_activity(
            tenant_id=booking.tenant_id,
            lead_id=booking.lead_id,
            contact_id=booking.contact_id,
            activity_type=activity_type,
            title=activity_title(activity_type),
            description=description,
            payload={
                "booking_id": booking.id,
                "provider": booking.provider,
                "start_at": booking.start_at.isoformat(),
                "status": booking.status,
            },
        )

    def map_calcom_response_to_crm_booking(self, booking: CrmBooking, result: dict[str, Any]) -> None:
        fields = calcom_booking_fields(result)
        booking.provider_booking_id = fields["provider_booking_id"] or booking.provider_booking_id
        booking.provider_booking_uid = fields["provider_booking_uid"] or booking.provider_booking_uid
        booking.status = fields["status"]
        booking.meeting_url = fields["meeting_url"]
        booking.host_name = fields["host_name"]
        booking.host_email = fields["host_email"]
        self.db.commit()
        self.db.refresh(booking)

    def _calcom_payload(
        self,
        *,
        config: CalComClientConfig,
        booking: CrmBooking,
        command: CreateBookingCommand,
        event_type_id: int | str | None,
        event_type_slug: str | None,
        username: str | None,
        team_slug: str | None,
        organization_slug: str | None,
        attendee_timezone: str | None = None,
    ) -> dict[str, Any]:
        return calcom_create_payload(
            start_at=booking.start_at,
            attendee_name=command.attendee_name,
            attendee_email=command.attendee_email,
            attendee_phone=command.attendee_phone,
            attendee_timezone=attendee_timezone or command.timezone or config.timezone,
            language=config.language,
            booking_fields_responses=command.booking_fields_responses,
            booking_id=booking.id,
            lead_id=booking.lead_id,
            contact_id=booking.contact_id,
            event_type_id=event_type_id,
            event_type_slug=event_type_slug,
            username=username,
            team_slug=team_slug,
            organization_slug=organization_slug,
        )

    # ------------------------------------------------------------------
    # Cancel / reschedule
    # ------------------------------------------------------------------
    def cancel_lead_booking(self, *, tenant_id: str, booking_id: str) -> dict[str, Any]:
        booking = self.get_booking(tenant_id=tenant_id, booking_id=booking_id)

        if booking_is_google(booking.provider, booking.google_calendar_event_id):
            GoogleCalendarProvider(self.db, tenant_id=tenant_id).cancel_booking(booking=booking)
            self.record_crm_activity(booking, "booking_created", "Reserva cancelada manualmente desde el CRM")
            self.record_crm_booking_event(booking, "booking_cancelled", booking.status, {"status": "cancelled"})
            self._publish_booking_event_safely(
                tenant_id=tenant_id, booking_id=booking.id, event_type=BOOKING_EVENT_CANCELLED
            )
            return {"status": "success", "booking_id": booking.id}

        _config, client_config, _ = self._effective_config(tenant_id)
        result = self.calcom_client.cancel_booking(client_config, booking.provider_booking_uid)  # type: ignore[arg-type]
        self.map_calcom_response_to_crm_booking(booking, result)
        booking.status = "cancelled"
        self.db.commit()
        self.db.refresh(booking)
        self.record_crm_activity(booking, "booking_created", "Reserva cancelada manualmente desde el CRM")
        self.record_crm_booking_event(booking, "booking_cancelled", booking.status, safe_provider_summary(result))
        self._publish_booking_event_safely(
            tenant_id=tenant_id, booking_id=booking.id, event_type=BOOKING_EVENT_CANCELLED
        )
        return {"status": "success", "booking_id": booking.id}

    def reschedule_lead_booking(
        self, *, tenant_id: str, booking_id: str, new_start_time: str
    ) -> dict[str, Any]:
        booking = self.get_booking(tenant_id=tenant_id, booking_id=booking_id)

        new_start_at = parse_utc_start(new_start_time)
        if booking_is_google(booking.provider, booking.google_calendar_event_id):
            GoogleCalendarProvider(self.db, tenant_id=tenant_id).reschedule_booking(
                booking=booking, new_start_at=new_start_at
            )
            self.record_crm_activity(booking, "booking_created", "Reserva reprogramada desde el CRM")
            self.record_crm_booking_event(
                booking, "booking_rescheduled", booking.status, {"status": "scheduled", "start_at": new_start_time}
            )
            self._publish_booking_event_safely(
                tenant_id=tenant_id, booking_id=booking.id, event_type=BOOKING_EVENT_RESCHEDULED
            )
            return {"status": "success", "booking_id": booking.id}

        config, client_config, _ = self._effective_config(tenant_id)
        result = self.calcom_client.reschedule_booking(client_config, booking.provider_booking_uid, new_start_time)  # type: ignore[arg-type]
        self.map_calcom_response_to_crm_booking(booking, result)
        booking.status = "scheduled"

        duration_minutes = booking.duration_minutes or config.default_length_minutes
        booking.start_at = new_start_at
        booking.end_at = new_start_at + timedelta(minutes=duration_minutes)
        self.db.commit()
        self.db.refresh(booking)

        self.record_crm_activity(booking, "booking_created", "Reserva reprogramada desde el CRM")
        self.record_crm_booking_event(
            booking, "booking_rescheduled", booking.status, safe_provider_summary(result)
        )
        self._publish_booking_event_safely(
            tenant_id=tenant_id, booking_id=booking.id, event_type=BOOKING_EVENT_RESCHEDULED
        )
        return {"status": "success", "booking_id": booking.id}

