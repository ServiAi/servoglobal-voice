from __future__ import annotations

import httpx
from unittest.mock import patch

from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
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
