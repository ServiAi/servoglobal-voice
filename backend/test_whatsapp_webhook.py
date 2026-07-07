from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.models.crm import CrmActivity, CrmWhatsAppMessage
from app.models.integrations import TenantIntegrationEvent, TenantWhatsAppConfig


class WhatsAppWebhookTests(Integration2ATestCase):
    def configure_whatsapp(self):
        with SessionLocal() as db:
            config = TenantWhatsAppConfig(
                tenant_id=self.tenant.id,
                provider="whatsapp_cloud",
                status="active",
                phone_number_id="phone-number-1",
                display_phone_number="+573001112233",
                default_language="es",
            )
            db.add(config)
            db.commit()

    def test_whatsapp_webhook_verify_uses_global_token(self):
        response = self.client.get(
            "/api/v1/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=serviglobal_whatsapp_webhook_token&hub.challenge=123"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), 123)

    def test_whatsapp_webhook_status_updates_message_activity_and_event(self):
        self.configure_whatsapp()
        lead_id, contact_id = self.seed_lead()
        with SessionLocal() as db:
            message = CrmWhatsAppMessage(
                tenant_id=self.tenant.id,
                lead_id=lead_id,
                contact_id=contact_id,
                provider_message_id="wamid.status-1",
                direction="outbound",
                to_phone="+573001112233",
                status="sent",
                metadata_json={},
                sent_at=datetime.now(timezone.utc),
            )
            db.add(message)
            db.commit()

        response = self.client.post(
            "/api/v1/webhook/whatsapp",
            json={"entry": [{"changes": [{"value": {"statuses": [{"id": "wamid.status-1", "status": "delivered"}]}}]}]},
        )

        self.assertEqual(response.status_code, 200)
        with SessionLocal() as db:
            message = db.scalar(select(CrmWhatsAppMessage).where(CrmWhatsAppMessage.provider_message_id == "wamid.status-1"))
            activity = db.scalar(select(CrmActivity).where(CrmActivity.activity_type == "whatsapp_status_delivered"))
            event = db.scalar(select(TenantIntegrationEvent).where(TenantIntegrationEvent.event_type == "whatsapp_status_delivered"))
        self.assertEqual(message.status, "delivered")
        self.assertIsNotNone(message.delivered_at)
        self.assertIsNotNone(activity)
        self.assertIsNotNone(event)

    def test_whatsapp_webhook_inbound_associates_safe_contact_without_creating_lead(self):
        self.configure_whatsapp()
        lead_id, _ = self.seed_lead()

        response = self.client.post(
            "/api/v1/webhook/whatsapp",
            json={
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "metadata": {"phone_number_id": "phone-number-1"},
                                    "messages": [
                                        {"id": "wamid.in-1", "from": "573001112233", "text": {"body": "Hola"}}
                                    ],
                                }
                            }
                        ]
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        with SessionLocal() as db:
            message = db.scalar(select(CrmWhatsAppMessage).where(CrmWhatsAppMessage.provider_message_id == "wamid.in-1"))
            lead_count = db.scalar(select(func.count()).select_from(__import__("app.models.crm", fromlist=["CrmLead"]).CrmLead))
        self.assertIsNotNone(message)
        self.assertEqual(message.lead_id, lead_id)
        self.assertEqual(lead_count, 1)

    def test_whatsapp_webhook_unmatched_inbound_does_not_create_lead(self):
        self.configure_whatsapp()

        response = self.client.post(
            "/api/v1/webhook/whatsapp",
            json={
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "metadata": {"phone_number_id": "phone-number-1"},
                                    "messages": [
                                        {"id": "wamid.in-2", "from": "573009990000", "text": {"body": "Nuevo"}}
                                    ],
                                }
                            }
                        ]
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        with SessionLocal() as db:
            lead_count = db.scalar(select(func.count()).select_from(__import__("app.models.crm", fromlist=["CrmLead"]).CrmLead))
            event = db.scalar(select(TenantIntegrationEvent).where(TenantIntegrationEvent.event_type == "whatsapp_inbound_unmatched"))
        self.assertEqual(lead_count, 0)
        self.assertIsNotNone(event)


if __name__ == "__main__":
    import unittest

    unittest.main()
