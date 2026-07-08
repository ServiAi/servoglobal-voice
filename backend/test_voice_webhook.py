from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.models.integrations import TenantIntegrationEvent
from app.models.crm import CrmActivity, CrmVoiceCall


class VoiceWebhookSafetyTests(Integration2ATestCase):
    def test_voice_webhook_unreconciled_does_not_create_platform_tenant_event(self):
        from app.services.voice_webhook_service import VoiceWebhookService

        with SessionLocal() as db:
            service = VoiceWebhookService(db)
            result = service.handle_provider_event("ultravox", {"event": "call.ended", "call": {"id": "unknown-call"}})

        with SessionLocal() as db:
            events = db.scalar(
                __import__("sqlalchemy", fromlist=["select"]).select(TenantIntegrationEvent).where(
                    TenantIntegrationEvent.tenant_id == "platform"
                )
            )
        self.assertIsNone(events)

    def test_voice_webhook_unreconciled_returns_safe_response(self):
        from app.services.voice_webhook_service import VoiceWebhookService

        with SessionLocal() as db:
            service = VoiceWebhookService(db)
            result = service.handle_provider_event("ultravox", {"event": "call.ended", "call": {"id": "unknown-call"}})

        self.assertEqual(result["status"], "unreconciled")
        self.assertFalse(result["processed"])

    def test_voice_webhook_unreconciled_does_not_create_crm_activity(self):
        from app.services.voice_webhook_service import VoiceWebhookService

        with SessionLocal() as db:
            service = VoiceWebhookService(db)
            service.handle_provider_event("ultravox", {"event": "call.ended", "call": {"id": "unknown-call"}})

        with SessionLocal() as db:
            activities = db.scalar(
                __import__("sqlalchemy", fromlist=["select"]).select(CrmActivity).where(
                    CrmActivity.activity_type == "voice_call_completed"
                )
            )
        self.assertIsNone(activities)

    def test_voice_webhook_unreconciled_does_not_create_voice_call_event(self):
        from app.services.voice_webhook_service import VoiceWebhookService
        from app.models.crm import CrmVoiceCallEvent

        with SessionLocal() as db:
            service = VoiceWebhookService(db)
            service.handle_provider_event("ultravox", {"event": "call.ended", "call": {"id": "unknown-call"}})

        with SessionLocal() as db:
            events = db.scalar(
                __import__("sqlalchemy", fromlist=["select"]).select(CrmVoiceCallEvent).where(
                    CrmVoiceCallEvent.event_type == "webhook_unreconciled"
                )
            )
        self.assertIsNone(events)


class VoiceWebhookErrorSanitizationTests(Integration2ATestCase):
    def test_voice_webhook_error_response_does_not_expose_exception_details(self):
        from app.services.voice_webhook_service import VoiceWebhookService

        with patch.object(VoiceWebhookService, "handle_provider_event") as mock_handle:
            mock_handle.side_effect = RuntimeError("Internal database connection pool exhausted")

            response = self.client.post(
                "/api/v1/voice/webhook/ultravox",
                json={"event": "call.ended", "call": {"id": "test"}},
            )

            self.assertEqual(response.status_code, 500)
            data = response.json()
            self.assertNotIn("database connection pool", data.get("detail", "").lower())
            self.assertNotIn("RuntimeError", data.get("detail", ""))


if __name__ == "__main__":
    unittest.main()
