from __future__ import annotations

from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.models.integrations import TenantIntegrationEvent
from app.schemas.integrations import ChatwootConfigRequest
from app.services.chatwoot_config_service import ChatwootConfigService


class ChatwootWebhookTests(Integration2ATestCase):
    def _configure(self, *, account_id: int = 17) -> str:
        with SessionLocal() as db:
            response = ChatwootConfigService(db).upsert_config(
                self.tenant.id,
                ChatwootConfigRequest(
                    base_url="https://crm.serviglobal-ia.com",
                    account_id=account_id,
                    default_inbox_id=35,
                    status="active",
                    api_token="cw_secret_token_1234567890",
                ),
            )
        return response.webhook_url.rsplit("/", 1)[-1]

    def test_unknown_webhook_key_returns_404(self):
        response = self.client.post(
            "/api/v1/webhooks/chatwoot/does-not-exist",
            json={"event": "message_created"},
        )
        self.assertEqual(response.status_code, 404)

    def test_account_id_mismatch_returns_401_and_records_event(self):
        webhook_key = self._configure(account_id=17)
        response = self.client.post(
            f"/api/v1/webhooks/chatwoot/{webhook_key}",
            json={
                "event": "message_created",
                "message_type": "incoming",
                "account": {"id": 999},
                "conversation": {"id": 1},
                "content": "hola",
            },
        )
        self.assertEqual(response.status_code, 401)
        with SessionLocal() as db:
            event = db.scalar(
                select(TenantIntegrationEvent).where(TenantIntegrationEvent.event_type == "webhook_rejected")
            )
        self.assertIsNotNone(event)
        self.assertEqual(event.tenant_id, self.tenant.id)

    def test_matching_account_id_processes_incoming_message_and_records_event(self):
        webhook_key = self._configure(account_id=17)
        response = self.client.post(
            f"/api/v1/webhooks/chatwoot/{webhook_key}",
            json={
                "event": "message_created",
                "message_type": "incoming",
                "account": {"id": 17},
                "conversation": {"id": 123},
                "content": "Hola, quiero info",
                "contact": {"name": "Juan", "phone_number": "+573001234567"},
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        with SessionLocal() as db:
            event = db.scalar(
                select(TenantIntegrationEvent).where(TenantIntegrationEvent.event_type == "webhook_received")
            )
        self.assertIsNotNone(event)
        self.assertEqual(event.resource_id, "123")

    def test_retried_message_created_delivery_is_not_processed_twice(self):
        webhook_key = self._configure(account_id=17)
        payload = {
            "id": 9001,
            "event": "message_created",
            "message_type": "incoming",
            "account": {"id": 17},
            "conversation": {"id": 123},
            "content": "Hola, quiero info",
        }

        first = self.client.post(f"/api/v1/webhooks/chatwoot/{webhook_key}", json=payload)
        second = self.client.post(f"/api/v1/webhooks/chatwoot/{webhook_key}", json=payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["status"], "ok")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json(), {"status": "ignored", "reason": "duplicate"})

        with SessionLocal() as db:
            events = list(
                db.scalars(
                    select(TenantIntegrationEvent).where(
                        TenantIntegrationEvent.event_type == "webhook_received",
                        TenantIntegrationEvent.resource_id == "9001",
                    )
                )
            )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].resource_type, "message")

    def test_non_incoming_message_is_ignored(self):
        webhook_key = self._configure(account_id=17)
        response = self.client.post(
            f"/api/v1/webhooks/chatwoot/{webhook_key}",
            json={
                "event": "message_created",
                "message_type": "outgoing",
                "account": {"id": 17},
                "conversation": {"id": 123},
                "content": "hola",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ignored")

    def test_other_event_types_are_ignored(self):
        webhook_key = self._configure(account_id=17)
        response = self.client.post(
            f"/api/v1/webhooks/chatwoot/{webhook_key}",
            json={"event": "conversation_status_changed", "account": {"id": 17}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ignored")

    def test_event_without_top_level_account_uses_nested_conversation_account(self):
        # conversation_typing_on/off (y otros) no traen "account" en el nivel
        # superior, solo anidado dentro de "conversation" (visto en produccion).
        webhook_key = self._configure(account_id=17)
        response = self.client.post(
            f"/api/v1/webhooks/chatwoot/{webhook_key}",
            json={
                "event": "conversation_typing_off",
                "user": {"id": 1, "name": "Agente"},
                "conversation": {"id": 15, "account": {"id": 17, "name": "Tenant"}},
                "is_private": False,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ignored")
        with SessionLocal() as db:
            rejected = db.scalar(
                select(TenantIntegrationEvent).where(TenantIntegrationEvent.event_type == "webhook_rejected")
            )
        self.assertIsNone(rejected)

    def test_event_without_any_account_still_rejected(self):
        webhook_key = self._configure(account_id=17)
        response = self.client.post(
            f"/api/v1/webhooks/chatwoot/{webhook_key}",
            json={"event": "conversation_typing_off", "conversation": {"id": 15}},
        )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    import unittest

    unittest.main()
