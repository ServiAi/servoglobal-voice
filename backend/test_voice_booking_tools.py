from __future__ import annotations

from unittest.mock import patch

from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.models.crm import CrmBooking
from app.models.integrations import TenantIntegrationEvent


class VoiceBookingToolsTests(Integration2ATestCase):
    def test_voice_availability_resolves_tenant_from_call_context_not_request_body(self):
        self.configure_calcom()
        other_tenant, _ = self._seed_tenant_user(slug="tenant-b", email="other@example.com")
        self.seed_lead(context_id="ctx-voice")
        self.seed_call_context(context_id="ctx-voice")

        with patch("app.services.booking_service.CalComClient.get_available_slots") as get_slots:
            get_slots.return_value = {
                "date": "2026-07-02",
                "jornada": "dia",
                "available_slots": [{"start": "2026-07-02T15:00:00Z"}],
                "summary": "1 slot",
            }
            response = self.client.post(
                "/api/v1/voice/tools/availability",
                json={
                    "tenant_id": other_tenant.id,
                    "call_context_id": "ctx-voice",
                    "date": "2026-07-02",
                    "jornada": "dia",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(get_slots.call_args.args[0].api_key, "cal_secret_test")
        with SessionLocal() as db:
            event = db.scalar(select(TenantIntegrationEvent).where(TenantIntegrationEvent.event_type == "availability_lookup"))
        self.assertEqual(event.tenant_id, self.tenant.id)

    def test_voice_booking_persists_booking_for_context_lead(self):
        self.configure_calcom()
        lead_id, _ = self.seed_lead(context_id="ctx-voice")
        self.seed_call_context(context_id="ctx-voice")

        with patch("app.services.booking_service.CalComClient.create_booking") as create_booking:
            create_booking.return_value = {
                "data": {"id": 789, "uid": "voice_uid_1", "status": "accepted"}
            }
            response = self.client.post(
                "/api/v1/voice/tools/bookings",
                json={
                    "call_context_id": "ctx-voice",
                    "start": "2026-07-02T15:00:00Z",
                    "attendee_name": "Pedro Gomez",
                    "attendee_email": "lead@example.com",
                    "attendee_phone": "+573001112233",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "accepted")
        with SessionLocal() as db:
            booking = db.scalar(select(CrmBooking).where(CrmBooking.lead_id == lead_id))
        self.assertEqual(booking.provider_booking_uid, "voice_uid_1")
        self.assertEqual(booking.calendar_mode, "cal_managed")

    def test_voice_booking_rejects_unresolved_tenant(self):
        response = self.client.post(
            "/api/v1/voice/tools/bookings",
            json={
                "call_context_id": "missing",
                "start": "2026-07-02T15:00:00Z",
                "attendee_name": "Pedro Gomez",
                "attendee_email": "lead@example.com",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("Unable to resolve tenant", response.text)
