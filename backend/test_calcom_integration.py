from __future__ import annotations

from datetime import UTC, datetime
import hmac
import httpx
import json
import os
from unittest.mock import patch

from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.models.crm import CrmActivity, CrmBooking, CrmBookingEvent
from app.models.integrations import TenantBookingConfig, TenantIntegrationEvent
from app.services.calcom_client import CalComClient, CalComClientConfig


class CalComIntegrationTests(Integration2ATestCase):
    def test_calcom_config_is_tenant_scoped_and_does_not_expose_secret(self):
        response = self.client.post(
            "/api/v1/integrations/calcom/config",
            json={
                "status": "active",
                "calendar_mode": "cal_managed",
                "cal_api_key": "cal_secret_test",
                "default_event_type_id": 123,
                "default_timezone": "America/Bogota",
                "default_language": "es",
                "default_length_minutes": 30,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["has_secret"])
        self.assertNotIn("cal_api_key", payload)
        self.assertNotIn("cal_secret_test", response.text)

        with SessionLocal() as db:
            config = db.scalar(select(TenantBookingConfig).where(TenantBookingConfig.tenant_id == self.tenant.id))
            events = list(db.scalars(select(TenantIntegrationEvent).where(TenantIntegrationEvent.provider == "calcom")))
        self.assertIsNotNone(config)
        self.assertNotIn("cal_secret_test", config.cal_api_key_encrypted)
        self.assertEqual(len(events), 1)

    def test_calcom_slots_use_authenticated_tenant_config(self):
        self.configure_calcom()
        with patch("app.services.booking_service.CalComClient.get_available_slots") as get_slots:
            get_slots.return_value = {
                "date": "2026-07-02",
                "jornada": "dia",
                "available_slots": [{"start": "2026-07-02T15:00:00Z"}],
                "summary": "1 slot",
            }
            response = self.client.get("/api/v1/integrations/calcom/slots?date=2026-07-02&jornada=dia")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["available_slots"][0]["start"], "2026-07-02T15:00:00Z")
        config_arg = get_slots.call_args.args[0]
        self.assertEqual(config_arg.api_key, "cal_secret_test")

    def test_calcom_slots_use_current_slots_api_version_header(self):
        with patch("app.services.calcom_client.httpx.get") as get:
            get.return_value = httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {
                        "2026-07-03": [
                            {"start": "2026-07-03T10:00:00.000-05:00"},
                        ],
                    },
                },
            )

            CalComClient(base_url="https://api.cal.com/v2").get_available_slots(
                CalComClientConfig(
                    api_key="cal_secret_test",
                    event_type_id=4797166,
                    api_version="2024-08-13",
                ),
                date_input="2026-07-03",
            )

        self.assertEqual(get.call_args.kwargs["headers"]["cal-api-version"], "2024-09-04")

    def test_calcom_test_connection_marks_health_without_leaking_secret(self):
        self.configure_calcom()
        with patch("app.services.booking_config_service.CalComClient.get_available_slots", return_value={"available_slots": []}):
            response = self.client.post("/api/v1/integrations/calcom/test")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("cal_secret_test", response.text)
        with SessionLocal() as db:
            config = db.scalar(select(TenantBookingConfig).where(TenantBookingConfig.tenant_id == self.tenant.id))
        self.assertEqual(config.status, "active")
        self.assertIsNotNone(config.last_health_check_at)

    def test_calcom_test_without_config_returns_422(self):
        response = self.client.post("/api/v1/integrations/calcom/test")

        self.assertEqual(response.status_code, 422)
        self.assertIn("Cal.com booking config is not active", response.json()["detail"])

    def test_calcom_webhook_updates_crm_booking_when_metadata_matches(self):
        lead_id, contact_id = self.seed_lead()
        with SessionLocal() as db:
            booking = CrmBooking(
                tenant_id=self.tenant.id,
                lead_id=lead_id,
                contact_id=contact_id,
                provider="calcom",
                status="pending",
                start_at=datetime(2026, 7, 2, 15, 0, tzinfo=UTC),
                end_at=datetime(2026, 7, 2, 15, 30, tzinfo=UTC),
                timezone="America/Bogota",
                attendee_name="Pedro Gomez",
                attendee_email="lead@example.com",
                calendar_mode="cal_managed",
            )
            db.add(booking)
            db.commit()
            db.refresh(booking)
            booking_id = booking.id

        payload = {
            "triggerEvent": "BOOKING_CREATED",
            "payload": {
                "id": 123,
                "uid": "cal_uid_1",
                "status": "accepted",
                "startTime": "2026-07-02T15:00:00Z",
                "meetingUrl": "https://meet.example/cal_uid_1",
                "metadata": {
                    "crm_booking_id": booking_id,
                    "crm_lead_id": lead_id,
                    "source": "serviglobal_crm",
                },
                "attendees": [{"name": "Pedro Gomez", "email": "lead@example.com"}],
                "responses": {"phone": {"value": "+573001112233"}},
            },
        }

        with patch.dict(os.environ, {"CALCOM_WEBHOOK_SECRET": ""}), patch(
            "app.services.notification_service.notification_service.notify_new_booking"
        ):
            response = self.client.post("/api/v1/calcom/webhook", json=payload)

        self.assertEqual(response.status_code, 200)
        with SessionLocal() as db:
            booking = db.get(CrmBooking, booking_id)
            event = db.scalar(select(CrmBookingEvent).where(CrmBookingEvent.booking_id == booking_id))
            activity = db.scalar(select(CrmActivity).where(CrmActivity.lead_id == lead_id, CrmActivity.activity_type == "booking_webhook"))
        self.assertEqual(booking.status, "accepted")
        self.assertEqual(booking.provider_booking_uid, "cal_uid_1")
        self.assertEqual(booking.meeting_url, "https://meet.example/cal_uid_1")
        self.assertIsNotNone(event)
        self.assertEqual(event.status, "accepted")
        self.assertNotIn("attendees", event.payload_summary_json)
        self.assertIsNotNone(activity)
        self.assertNotIn("lead@example.com", json.dumps(activity.payload_json))
        self.assertNotIn("+573001112233", json.dumps(activity.payload_json))

    def test_calcom_webhook_does_not_log_full_payload(self):
        payload = {
            "triggerEvent": "BOOKING_CREATED",
            "payload": {
                "startTime": "2026-07-02T15:00:00Z",
                "attendees": [{"name": "Pedro Gomez", "email": "lead@example.com"}],
                "responses": {"phone": {"value": "+573001112233"}},
            },
        }

        with patch.dict(os.environ, {"CALCOM_WEBHOOK_SECRET": ""}), patch(
            "app.services.notification_service.notification_service.notify_new_booking"
        ), patch("app.api.endpoints.calcom.logger.debug") as debug_log, patch(
            "app.api.endpoints.calcom.logger.info"
        ) as info_log, patch("app.api.endpoints.calcom.logger.warning") as warning_log:
            response = self.client.post("/api/v1/calcom/webhook", json=payload)

        self.assertEqual(response.status_code, 200)
        logged = " ".join(
            str(call)
            for logger_mock in (debug_log, info_log, warning_log)
            for call in logger_mock.call_args_list
        )
        self.assertNotIn("Pedro Gomez", logged)
        self.assertNotIn("lead@example.com", logged)
        self.assertNotIn("+573001112233", logged)
        self.assertNotIn(json.dumps(payload), logged)

    def test_calcom_webhook_rejects_invalid_signature_when_secret_configured(self):
        body = json.dumps({"triggerEvent": "BOOKING_CREATED", "payload": {}}).encode("utf-8")
        valid_signature = hmac.new(b"hook-secret", body, digestmod="sha256").hexdigest()

        with patch.dict(os.environ, {"CALCOM_WEBHOOK_SECRET": "hook-secret"}):
            invalid_signature = valid_signature[:-1] + ("0" if valid_signature[-1] != "0" else "1")
            response = self.client.post(
                "/api/v1/calcom/webhook",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Cal-Signature-256": invalid_signature,
                },
            )

        self.assertEqual(response.status_code, 403)
