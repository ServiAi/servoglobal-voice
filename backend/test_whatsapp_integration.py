from __future__ import annotations

from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.models.integrations import TenantIntegrationEvent, TenantWhatsAppConfig
from app.services.whatsapp_client import sanitize_whatsapp_error


class WhatsAppIntegrationTests(Integration2ATestCase):
    def _payload(self, token: str | None = "EA_secret_token_12345678901234567890"):
        return {
            "phone_number_id": "phone-number-1",
            "business_account_id": "waba-1",
            "display_phone_number": "+573001112233",
            "default_language": "es",
            "status": "active",
            "access_token": token,
        }

    def test_whatsapp_config_encrypts_token_and_does_not_expose_it(self):
        response = self.client.post("/api/v1/integrations/whatsapp/config", json=self._payload())

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["has_secret"])
        self.assertNotIn("EA_secret_token", response.text)
        with SessionLocal() as db:
            config = db.scalar(select(TenantWhatsAppConfig).where(TenantWhatsAppConfig.tenant_id == self.tenant.id))
            event = db.scalar(select(TenantIntegrationEvent).where(TenantIntegrationEvent.provider == "whatsapp_cloud"))
        self.assertIsNotNone(config)
        self.assertNotIn("EA_secret_token", config.access_token_encrypted)
        self.assertIsNotNone(event)

    def test_whatsapp_config_requires_token_only_first_time_and_preserves_existing(self):
        first = self.client.post("/api/v1/integrations/whatsapp/config", json=self._payload())
        self.assertEqual(first.status_code, 200)
        with SessionLocal() as db:
            before = db.scalar(select(TenantWhatsAppConfig).where(TenantWhatsAppConfig.tenant_id == self.tenant.id)).access_token_encrypted

        second_payload = self._payload(token=None)
        second_payload["display_phone_number"] = "+573009998888"
        second = self.client.post("/api/v1/integrations/whatsapp/config", json=second_payload)

        self.assertEqual(second.status_code, 200)
        with SessionLocal() as db:
            config = db.scalar(select(TenantWhatsAppConfig).where(TenantWhatsAppConfig.tenant_id == self.tenant.id))
        self.assertEqual(config.access_token_encrypted, before)
        self.assertEqual(config.display_phone_number, "+573009998888")

    def test_whatsapp_config_without_initial_token_returns_422(self):
        response = self.client.post("/api/v1/integrations/whatsapp/config", json=self._payload(token=None))

        self.assertEqual(response.status_code, 422)

    def test_whatsapp_test_connection_marks_health_with_mock(self):
        self.client.post("/api/v1/integrations/whatsapp/config", json=self._payload())
        from app.services.whatsapp_client import WhatsAppCloudClient

        class _Client(WhatsAppCloudClient):
            def get_phone_number_info(self, config):
                return {"display_phone_number": "+573001112233"}

        with SessionLocal() as db:
            from app.services.whatsapp_config_service import WhatsAppConfigService

            result = WhatsAppConfigService(db, client=_Client()).test_connection(self.tenant.id)

        self.assertEqual(result.status, "success")
        with SessionLocal() as db:
            config = db.scalar(select(TenantWhatsAppConfig).where(TenantWhatsAppConfig.tenant_id == self.tenant.id))
        self.assertIsNotNone(config.last_health_check_at)

    def test_whatsapp_error_sanitizer_redacts_token_phone_and_email(self):
        sanitized = sanitize_whatsapp_error(
            "Bearer EA_secret_token_12345678901234567890 person@example.com +57 300 123 4567"
        )

        self.assertNotIn("EA_secret_token", sanitized)
        self.assertNotIn("person@example.com", sanitized)
        self.assertNotIn("+57 300 123 4567", sanitized)


if __name__ == "__main__":
    import unittest

    unittest.main()
