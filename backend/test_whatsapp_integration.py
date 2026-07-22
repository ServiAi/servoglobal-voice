from __future__ import annotations

from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.models.integrations import TenantIntegrationEvent, TenantWhatsAppConfig, TenantWhatsAppTemplate
from app.services.whatsapp_client import WhatsAppCloudClient, sanitize_whatsapp_error


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

    def test_whatsapp_connection_test_does_not_send_message_and_explains_it(self):
        self.client.post("/api/v1/integrations/whatsapp/config", json=self._payload())

        class _Client(WhatsAppCloudClient):
            sent = False

            def get_phone_number_info(self, config):
                return {"display_phone_number": "+573001112233"}

            def send_template_message(self, *args, **kwargs):
                self.sent = True
                return {}

        client = _Client()
        with SessionLocal() as db:
            from app.services.whatsapp_config_service import WhatsAppConfigService

            result = WhatsAppConfigService(db, client=client).test_connection(self.tenant.id)

        self.assertEqual(result.status, "success")
        self.assertFalse(result.sends_message)
        self.assertIn("no envía mensajes", result.message)
        self.assertFalse(client.sent)

    def test_sync_whatsapp_templates_requires_business_account_id(self):
        payload = self._payload()
        payload["business_account_id"] = None
        self.client.post("/api/v1/integrations/whatsapp/config", json=payload)

        response = self.client.post("/api/v1/integrations/whatsapp/templates/sync")

        self.assertEqual(response.status_code, 422)
        self.assertIn("WABA ID", response.json()["detail"])

    def test_sync_whatsapp_templates_fetches_filters_upserts_and_records_event(self):
        self.client.post("/api/v1/integrations/whatsapp/config", json=self._payload())

        class _Client(WhatsAppCloudClient):
            def get_message_templates(self, config, *, business_account_id, limit=100):
                return {"data": [
                    {
                        "name": "appointment_reminder",
                        "status": "APPROVED",
                        "language": "es",
                        "category": "UTILITY",
                        "components": [{"type": "BODY", "text": "Hola {{1}}, cita {{2}}"}],
                    },
                    {"name": "draft_template", "status": "PENDING", "language": "es"},
                ]}

        with SessionLocal() as db:
            from app.services.whatsapp_config_service import WhatsAppConfigService

            service = WhatsAppConfigService(db, client=_Client())
            first = service.sync_templates(self.tenant.id)
            second = service.sync_templates(self.tenant.id)

        self.assertEqual((first.fetched_count, first.approved_count, first.synced_count, first.ignored_count), (2, 1, 1, 1))
        self.assertEqual(second.synced_count, 1)
        with SessionLocal() as db:
            templates = db.scalars(select(TenantWhatsAppTemplate).where(TenantWhatsAppTemplate.template_key == "appointment_reminder")).all()
            event = db.scalar(select(TenantIntegrationEvent).where(TenantIntegrationEvent.event_type == "whatsapp_templates_sync"))
        self.assertEqual(len(templates), 1)
        self.assertEqual(templates[0].variables_json["parameters"][0]["key"], "1")
        self.assertIsNotNone(event)

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
