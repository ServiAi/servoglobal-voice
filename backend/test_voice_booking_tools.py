from __future__ import annotations

from unittest.mock import patch

from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.core.config import settings
from app.models.crm import CrmBooking
from app.models.integrations import TenantIntegrationEvent, TenantVoiceBookingConfig


class VoiceBookingToolsTests(Integration2ATestCase):
    def setUp(self):
        super().setUp()
        self._old_voice_secret = settings.VOICE_TOOL_SHARED_SECRET
        settings.VOICE_TOOL_SHARED_SECRET = "voice-secret-test"
        self.voice_headers = {"X-Voice-Tool-Secret": "voice-secret-test"}

    def tearDown(self):
        settings.VOICE_TOOL_SHARED_SECRET = self._old_voice_secret
        super().tearDown()

    def test_voice_tool_requires_secret(self):
        response = self.client.post(
            "/api/v1/voice/tools/availability",
            json={"call_context_id": "ctx-voice", "date": "2026-07-02"},
        )

        self.assertEqual(response.status_code, 401)

    def test_voice_tool_rejects_invalid_secret(self):
        response = self.client.post(
            "/api/v1/voice/tools/availability",
            headers={"X-Voice-Tool-Secret": "bad-secret"},
            json={"call_context_id": "ctx-voice", "date": "2026-07-02"},
        )

        self.assertEqual(response.status_code, 401)

    def test_voice_tool_accepts_valid_secret(self):
        self.configure_calcom()
        self.seed_lead(context_id="ctx-voice")
        self.seed_call_context(context_id="ctx-voice")

        with patch("app.services.booking_service.CalComClient.get_available_slots") as get_slots:
            get_slots.return_value = {"date": "2026-07-02", "jornada": "all", "available_slots": [], "summary": ""}
            response = self.client.post(
                "/api/v1/voice/tools/availability",
                headers=self.voice_headers,
                json={"call_context_id": "ctx-voice", "date": "2026-07-02"},
            )

        self.assertEqual(response.status_code, 200)

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
                headers=self.voice_headers,
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

    def test_voice_availability_uses_agent_specific_config_when_available(self):
        self.configure_calcom()
        self.seed_lead(context_id="ctx-voice")
        self.seed_call_context(context_id="ctx-voice")
        with SessionLocal() as db:
            db.add(
                TenantVoiceBookingConfig(
                    tenant_id=self.tenant.id,
                    provider_agent_id="agent-voice-1",
                    default_event_type_id=999,
                    default_timezone="America/Mexico_City",
                    status="active",
                )
            )
            db.commit()

        with patch("app.services.booking_service.CalComClient.get_available_slots") as get_slots:
            get_slots.return_value = {"date": "2026-07-02", "jornada": "all", "available_slots": [], "summary": ""}
            response = self.client.post(
                "/api/v1/voice/tools/availability",
                headers=self.voice_headers,
                json={
                    "call_context_id": "ctx-voice",
                    "agent_id": "agent-voice-1",
                    "date": "2026-07-02",
                },
            )

        self.assertEqual(response.status_code, 200)
        config_arg = get_slots.call_args.args[0]
        self.assertEqual(config_arg.event_type_id, 999)
        self.assertEqual(config_arg.timezone, "America/Mexico_City")

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
                headers=self.voice_headers,
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

    def test_voice_booking_uses_agent_specific_event_type(self):
        self.configure_calcom()
        lead_id, _ = self.seed_lead(context_id="ctx-voice")
        self.seed_call_context(context_id="ctx-voice")
        with SessionLocal() as db:
            db.add(
                TenantVoiceBookingConfig(
                    tenant_id=self.tenant.id,
                    provider_agent_id="agent-voice-1",
                    default_event_type_id=999,
                    default_timezone="America/Mexico_City",
                    status="active",
                )
            )
            db.commit()

        with patch("app.services.booking_service.CalComClient.create_booking") as create_booking:
            create_booking.return_value = {"data": {"id": 789, "uid": "voice_uid_1", "status": "accepted"}}
            response = self.client.post(
                "/api/v1/voice/tools/bookings",
                headers=self.voice_headers,
                json={
                    "call_context_id": "ctx-voice",
                    "agent_id": "agent-voice-1",
                    "start": "2026-07-02T15:00:00Z",
                    "attendee_name": "Pedro Gomez",
                    "attendee_email": "lead@example.com",
                },
            )

        self.assertEqual(response.status_code, 200)
        provider_payload = create_booking.call_args.args[1]
        self.assertEqual(provider_payload["eventTypeId"], 999)
        self.assertEqual(provider_payload["attendee"]["timeZone"], "America/Mexico_City")
        with SessionLocal() as db:
            booking = db.scalar(select(CrmBooking).where(CrmBooking.lead_id == lead_id))
        self.assertEqual(booking.provider_event_type_id, "999")

    def test_voice_booking_rejects_unresolved_tenant(self):
        response = self.client.post(
            "/api/v1/voice/tools/bookings",
            headers=self.voice_headers,
            json={
                "call_context_id": "missing",
                "start": "2026-07-02T15:00:00Z",
                "attendee_name": "Pedro Gomez",
                "attendee_email": "lead@example.com",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("Unable to resolve tenant", response.text)
