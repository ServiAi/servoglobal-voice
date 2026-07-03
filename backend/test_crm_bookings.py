from __future__ import annotations

from unittest.mock import patch

from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.models.crm import CrmBooking, CrmBookingEvent


class CrmBookingTests(Integration2ATestCase):
    def test_lead_booking_creates_crm_record_and_sends_safe_calcom_payload(self):
        self.configure_calcom()
        lead_id, _ = self.seed_lead()

        with patch("app.services.booking_service.CalComClient.create_booking") as create_booking:
            create_booking.return_value = {
                "data": {
                    "id": 456,
                    "uid": "booking_uid_1",
                    "status": "accepted",
                    "meetingUrl": "https://meet.example/booking_uid_1",
                }
            }
            response = self.client.post(
                f"/api/v1/crm/leads/{lead_id}/bookings",
                json={
                    "start": "2026-07-02T15:00:00Z",
                    "attendee_name": "Pedro Gomez",
                    "attendee_email": "lead@example.com",
                    "attendee_phone": "+573001112233",
                    "notes": "Demo inicial",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["provider_booking_uid"], "booking_uid_1")
        self.assertEqual(payload["status"], "accepted")

        provider_payload = create_booking.call_args.args[1]
        self.assertNotIn("tenant_id", provider_payload)
        self.assertNotIn("tenant_id", provider_payload["metadata"])
        self.assertEqual(provider_payload["metadata"]["crm_lead_id"], lead_id)
        self.assertEqual(provider_payload["attendee"]["email"], "lead@example.com")

        with SessionLocal() as db:
            booking = db.scalar(select(CrmBooking).where(CrmBooking.lead_id == lead_id))
            events = list(db.scalars(select(CrmBookingEvent).where(CrmBookingEvent.booking_id == booking.id)))
        self.assertEqual(booking.provider_booking_uid, "booking_uid_1")
        self.assertGreaterEqual(len(events), 2)

    def test_lead_booking_accepts_calcom_slot_timezone_offset(self):
        self.configure_calcom()
        lead_id, _ = self.seed_lead()

        with patch("app.services.booking_service.CalComClient.create_booking") as create_booking:
            create_booking.return_value = {"data": {"id": 456, "uid": "booking_uid_1", "status": "accepted"}}
            response = self.client.post(
                f"/api/v1/crm/leads/{lead_id}/bookings",
                json={
                    "start": "2026-07-05T09:00:00.000-05:00",
                    "attendee_name": "Pedro Gomez",
                    "attendee_email": "lead@example.com",
                },
            )

        self.assertEqual(response.status_code, 200)
        provider_payload = create_booking.call_args.args[1]
        self.assertEqual(provider_payload["start"], "2026-07-05T14:00:00Z")

    def test_booking_requires_contact_email(self):
        self.configure_calcom()
        lead_id, _ = self.seed_lead(email=None)

        response = self.client.post(
            f"/api/v1/crm/leads/{lead_id}/bookings",
            json={
                "start": "2026-07-02T15:00:00Z",
                "attendee_name": "Pedro Gomez",
                "attendee_email": "lead@example.com",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("Lead contact email is required", response.text)

    def test_booking_rejects_non_utc_start(self):
        self.configure_calcom()
        lead_id, _ = self.seed_lead()

        response = self.client.post(
            f"/api/v1/crm/leads/{lead_id}/bookings",
            json={
                "start": "2026-07-02T10:00:00-05:00",
                "attendee_name": "Pedro Gomez",
                "attendee_email": "lead@example.com",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("UTC", response.text)

    def test_google_insert_mode_is_not_enabled_for_booking_creation(self):
        self.configure_calcom(calendar_mode="crm_google_insert")
        lead_id, _ = self.seed_lead()

        response = self.client.post(
            f"/api/v1/crm/leads/{lead_id}/bookings",
            json={
                "start": "2026-07-02T15:00:00Z",
                "attendee_name": "Pedro Gomez",
                "attendee_email": "lead@example.com",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("Google Calendar insert mode is not enabled yet", response.text)
