"""Scheduling at its seams: CRM only as DTOs, Notifications only as a published
fact, providers faked, tenants isolated. Fakes + SQLite; no network."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from pydantic import ValidationError
from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.modules.scheduling.application import booking_service as booking_service_module
from app.modules.scheduling.application.booking_service import BookingService
from app.modules.scheduling.application.calcom_webhook import reconcile_calcom_webhook
from app.modules.scheduling.application.ports import SchedulingPorts
from app.modules.scheduling.domain.contracts import BookingCustomer, CreateBookingCommand
from app.modules.scheduling.domain.errors import BookingCustomerNotFoundError, BookingNotFoundError
from app.modules.scheduling.infrastructure.models import CrmBooking, CrmBookingEvent
from app.modules.scheduling.public import BookingView, SchedulingFacade


class FakeCustomers:
    def __init__(self, customers: dict[tuple[str, str], BookingCustomer]) -> None:
        self.customers = customers
        self.calls: list[tuple[str, str]] = []

    def get_booking_customer(self, tenant_id: str, lead_id: str) -> BookingCustomer:
        self.calls.append((tenant_id, lead_id))
        try:
            return self.customers[(tenant_id, lead_id)]
        except KeyError:
            raise BookingCustomerNotFoundError() from None


class FakeTimeline:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def record_activity(self, **kwargs) -> None:
        self.entries.append(kwargs)


class FakeEvents:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.events: list[tuple[str, str, str]] = []

    def publish_booking_event(self, *, tenant_id: str, booking_id: str, event_type: str) -> None:
        if self.error:
            raise self.error
        self.events.append((tenant_id, booking_id, event_type))


class FakeCalCom:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.created = 0

    def create_booking(self, config, payload):
        self.created += 1
        if self.fail:
            raise RuntimeError("Bearer cal_live_secret failed for lead@example.com")
        return {"data": {"id": 11, "uid": "uid-11", "status": "accepted", "meetingUrl": "https://meet/11"}}

    def cancel_booking(self, config, uid):
        return {"data": {"id": 11, "uid": uid, "status": "cancelled"}}

    def reschedule_booking(self, config, uid, start):
        return {"data": {"id": 11, "uid": uid, "status": "accepted"}}


def _command(**overrides) -> CreateBookingCommand:
    values = dict(start="2026-07-02T15:00:00Z", attendee_name="Pedro", attendee_email="lead@example.com")
    values.update(overrides)
    return CreateBookingCommand(**values)


class SchedulingBoundaryTests(Integration2ATestCase):
    def _ports(self, lead_id: str, contact_id: str, *, events: FakeEvents | None = None):
        customer = BookingCustomer(
            lead_id=lead_id, contact_id=contact_id, tenant_id=self.tenant.id,
            name="Pedro", email="lead@example.com", phone="+573001112233",
        )
        customers = FakeCustomers({(self.tenant.id, lead_id): customer})
        timeline, events = FakeTimeline(), events or FakeEvents()
        return SchedulingPorts(customer=customers, activity=timeline, events=events), customers, timeline, events

    def _service(self, db, ports, client=None) -> BookingService:
        return BookingService(db, ports=ports, calcom_client=client or FakeCalCom())

    # -- provider-agnostic flow with a fake adapter ---------------------------------
    def test_calcom_booking_flow_talks_to_crm_and_events_only_through_ports(self) -> None:
        self.configure_calcom()
        lead_id, contact_id = self.seed_lead()
        ports, customers, timeline, events = self._ports(lead_id, contact_id)
        with SessionLocal() as db:
            booking = self._service(db, ports).create_lead_booking(
                tenant_id=self.tenant.id, lead_id=lead_id, command=_command()
            )
            booking_id, status = booking.id, booking.status
        self.assertEqual(status, "accepted")
        self.assertEqual(customers.calls, [(self.tenant.id, lead_id)])
        self.assertEqual([e["activity_type"] for e in timeline.entries], ["booking_requested", "booking_created"])
        self.assertTrue(all(e["tenant_id"] == self.tenant.id and e["contact_id"] == contact_id for e in timeline.entries))
        self.assertEqual(events.events, [(self.tenant.id, booking_id, "booking.created")])

    def test_booking_history_is_owned_by_scheduling(self) -> None:
        self.configure_calcom()
        lead_id, contact_id = self.seed_lead()
        ports, *_ = self._ports(lead_id, contact_id)
        with SessionLocal() as db:
            booking_id = self._service(db, ports).create_lead_booking(
                tenant_id=self.tenant.id, lead_id=lead_id, command=_command()
            ).id
        with SessionLocal() as db:
            kinds = list(db.scalars(select(CrmBookingEvent.event_type).where(CrmBookingEvent.booking_id == booking_id).order_by(CrmBookingEvent.created_at)))
        self.assertEqual(kinds, ["booking_requested", "booking_created"])

    # -- tenant isolation -----------------------------------------------------------
    def test_a_foreign_or_unknown_lead_creates_nothing(self) -> None:
        self.configure_calcom()
        lead_id, contact_id = self.seed_lead()
        ports, *_ = self._ports(lead_id, contact_id)
        with SessionLocal() as db:
            with self.assertRaises(ValueError) as caught:
                self._service(db, ports).create_lead_booking(
                    tenant_id=self.tenant.id, lead_id="someone-elses-lead", command=_command()
                )
            self.assertEqual(str(caught.exception), "Lead not found")
            self.assertEqual(db.scalars(select(CrmBooking)).all(), [])

    def test_a_booking_of_another_tenant_is_not_found(self) -> None:
        self.configure_calcom()
        lead_id, contact_id = self.seed_lead()
        ports, *_ = self._ports(lead_id, contact_id)
        with SessionLocal() as db:
            booking_id = self._service(db, ports).create_lead_booking(
                tenant_id=self.tenant.id, lead_id=lead_id, command=_command()
            ).id
            facade = SchedulingFacade(db)
            with self.assertRaises(BookingNotFoundError):
                facade.get_booking(tenant_id="another-tenant", booking_id=booking_id)
            with self.assertRaises(ValueError):
                facade.cancel_booking(tenant_id="another-tenant", booking_id=booking_id)

    def test_contact_without_email_is_rejected_before_any_row_exists(self) -> None:
        self.configure_calcom()
        lead_id, contact_id = self.seed_lead()
        customer = BookingCustomer(lead_id=lead_id, contact_id=contact_id, tenant_id=self.tenant.id, name="P", email=None, phone=None)
        ports = SchedulingPorts(
            customer=FakeCustomers({(self.tenant.id, lead_id): customer}), activity=FakeTimeline(), events=FakeEvents()
        )
        with SessionLocal() as db:
            with self.assertRaisesRegex(ValueError, "email is required"):
                self._service(db, ports).create_lead_booking(tenant_id=self.tenant.id, lead_id=lead_id, command=_command())
            self.assertEqual(db.scalars(select(CrmBooking)).all(), [])

    # -- facts, not calls -------------------------------------------------------------
    def test_a_failing_event_publisher_never_affects_the_booking(self) -> None:
        self.configure_calcom()
        lead_id, contact_id = self.seed_lead()
        ports, *_ = self._ports(lead_id, contact_id, events=FakeEvents(error=RuntimeError("bus down")))
        with SessionLocal() as db:
            booking = self._service(db, ports).create_lead_booking(
                tenant_id=self.tenant.id, lead_id=lead_id, command=_command()
            )
            self.assertEqual(booking.status, "accepted")

    def test_a_provider_failure_records_history_but_announces_no_fact(self) -> None:
        self.configure_calcom()
        lead_id, contact_id = self.seed_lead()
        ports, _, timeline, events = self._ports(lead_id, contact_id)
        with SessionLocal() as db:
            with self.assertRaises(RuntimeError):
                self._service(db, ports, FakeCalCom(fail=True)).create_lead_booking(
                    tenant_id=self.tenant.id, lead_id=lead_id, command=_command()
                )
        self.assertEqual(events.events, [])
        failure = [e for e in timeline.entries if e["activity_type"] == "booking_failed"][0]
        self.assertNotIn("cal_live_secret", failure["description"])
        self.assertNotIn("lead@example.com", failure["description"])
        with SessionLocal() as db:
            self.assertEqual(db.scalars(select(CrmBooking)).one().status, "failed")

    def test_cancel_and_reschedule_announce_their_own_facts(self) -> None:
        self.configure_calcom()
        lead_id, contact_id = self.seed_lead()
        ports, _, _, events = self._ports(lead_id, contact_id)
        with SessionLocal() as db:
            service = self._service(db, ports)
            booking_id = service.create_lead_booking(tenant_id=self.tenant.id, lead_id=lead_id, command=_command()).id
            service.reschedule_lead_booking(tenant_id=self.tenant.id, booking_id=booking_id, new_start_time="2026-07-03T15:00:00Z")
            service.cancel_lead_booking(tenant_id=self.tenant.id, booking_id=booking_id)
        self.assertEqual([e[2] for e in events.events], ["booking.created", "booking.rescheduled", "booking.cancelled"])

    def test_scheduling_application_does_not_even_name_the_notification_pipeline(self) -> None:
        self.assertFalse(hasattr(booking_service_module, "NotificationEventPipeline"))
        self.assertFalse(hasattr(booking_service_module, "CrmActivityService"))
        self.assertFalse(hasattr(booking_service_module, "CrmLead"))

    # -- what crosses the public API -----------------------------------------------------
    def test_public_views_carry_no_provider_internals(self) -> None:
        self.configure_calcom()
        lead_id, contact_id = self.seed_lead()
        ports, *_ = self._ports(lead_id, contact_id)
        with SessionLocal() as db:
            booking_id = self._service(db, ports).create_lead_booking(
                tenant_id=self.tenant.id, lead_id=lead_id, command=_command()
            ).id
            row = db.get(CrmBooking, booking_id)
            row.metadata_json = {"source": "serviglobal_crm", "internal": "x", "notification_custom": {"plan": "gold"}}
            db.commit()
            view = SchedulingFacade(db).get_booking(tenant_id=self.tenant.id, booking_id=booking_id)
        self.assertIsInstance(view, BookingView)
        self.assertEqual(dict(view.notification_custom), {"plan": "gold"})
        self.assertFalse(hasattr(view, "metadata_json"))
        self.assertNotIn("internal", repr(view))

    def test_tool_flavoured_create_validates_untrusted_arguments(self) -> None:
        with SessionLocal() as db:
            facade = SchedulingFacade(db)
            with self.assertRaises(ValidationError):
                facade.create_lead_booking(
                    tenant_id=self.tenant.id, lead_id="l", start="2026-07-02T15:00:00Z",
                    attendee_name="P", attendee_email="p@example.com", attendee_phone=None,
                    notes={"llm": "sent an object"},  # type: ignore[arg-type]
                )

    # -- Cal.com webhook reconciliation lives in Scheduling ----------------------------------
    def test_calcom_webhook_updates_the_booking_through_scheduling(self) -> None:
        self.configure_calcom()
        lead_id, contact_id = self.seed_lead()
        ports, _, timeline, _ = self._ports(lead_id, contact_id)
        with SessionLocal() as db:
            booking_id = self._service(db, ports).create_lead_booking(
                tenant_id=self.tenant.id, lead_id=lead_id, command=_command()
            ).id
            payload = {
                "id": 11, "uid": "uid-11",
                "metadata": {"crm_booking_id": booking_id, "crm_lead_id": lead_id, "source": "serviglobal_crm"},
            }
            view = reconcile_calcom_webhook(db, "BOOKING_CANCELLED", payload, ports)
            self.assertEqual(view.status, "cancelled")
            self.assertEqual(timeline.entries[-1]["activity_type"], "booking_webhook")
            # not ours / not matching -> ignored
            self.assertIsNone(reconcile_calcom_webhook(db, "BOOKING_CANCELLED", {"metadata": {"source": "other"}}, ports))
            wrong_lead = {**payload, "metadata": {**payload["metadata"], "crm_lead_id": "other-lead"}}
            self.assertIsNone(reconcile_calcom_webhook(db, "BOOKING_CANCELLED", wrong_lead, ports))


if __name__ == "__main__":
    unittest.main()
