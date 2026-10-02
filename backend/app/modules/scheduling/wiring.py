"""Composition root of Scheduling: binds the ports to the other modules.

The only place that knows which concrete code answers "who is this lead?",
"write this to the CRM timeline" and "announce this booking fact". Application
code depends on the Protocols in ``application/ports.py`` only.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.modules.scheduling.application.ports import SchedulingPorts
from app.modules.scheduling.domain.contracts import BookingCustomer
from app.modules.scheduling.domain.errors import BookingCustomerNotFoundError

logger = logging.getLogger(__name__)


class CrmBookingCustomer:
    """BookingCustomerPort -> crm.public (DTOs; tenant checked here)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_booking_customer(self, tenant_id: str, lead_id: str) -> BookingCustomer:
        from app.modules.crm.public import CrmFacade

        crm = CrmFacade(self.db)
        lead = crm.get_lead(lead_id)
        # get_lead is not tenant-scoped: fail closed on a foreign lead.
        if lead is None or lead.tenant_id != tenant_id:
            raise BookingCustomerNotFoundError()
        contact = crm.get_contact(lead.contact_id)
        if contact is None:
            raise BookingCustomerNotFoundError()
        return BookingCustomer(
            lead_id=lead.id,
            contact_id=contact.id,
            tenant_id=lead.tenant_id,
            name=contact.name,
            email=contact.email,
            phone=contact.phone,
        )


class CrmTimeline:
    """CrmActivityPort -> crm.public."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def record_activity(
        self,
        *,
        tenant_id: str,
        lead_id: str | None,
        contact_id: str,
        activity_type: str,
        title: str,
        description: str | None,
        payload: dict,
    ) -> None:
        from app.modules.crm.public import CrmFacade

        CrmFacade(self.db).record_activity(
            tenant_id=tenant_id,
            lead_id=lead_id,
            contact_id=contact_id,
            activity_type=activity_type,
            title=title,
            description=description,
            payload=payload,
        )


class NotificationBookingEvents:
    """BookingEventPublisherPort -> the existing domain-event pipeline.

    Scheduling announces the fact; the platform's domain-event infrastructure
    (``domain_events`` + the notification pipeline, with its idempotency keys
    ``booking:{id}:created|cancelled|rescheduled:{digest}``) reacts. This
    adapter is the single temporary bridge, retired when Notifications
    subscribes to ``domain_events`` on its own (see MODULAR_MONOLITH_MIGRATION).
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def publish_booking_event(self, *, tenant_id: str, booking_id: str, event_type: str) -> None:
        from app.services.notification_event_pipeline import NotificationEventPipeline

        NotificationEventPipeline(self.db).process_booking_event(
            tenant_id=tenant_id, booking_id=booking_id, event_type=event_type
        )


def default_scheduling_ports(db: Session) -> SchedulingPorts:
    return SchedulingPorts(
        customer=CrmBookingCustomer(db),
        activity=CrmTimeline(db),
        events=NotificationBookingEvents(db),
    )


def run_booking_event_task(*, tenant_id: str, booking_id: str, event_type: str) -> None:
    """Background-task entry point to announce a booking fact (opens its own
    session; never raises). Used by the Cal.com webhook."""
    from app.services.notification_event_pipeline import run_booking_notification_pipeline_task

    run_booking_notification_pipeline_task(tenant_id=tenant_id, booking_id=booking_id, event_type=event_type)
