from __future__ import annotations

from sqlalchemy import func, select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.models.crm import CrmActivity, CrmWhatsAppMessage
from app.models.integrations import TenantIntegrationEvent, TenantWhatsAppTemplate
from app.schemas.integrations import WhatsAppTestMessageRequest
from app.services.whatsapp_client import WhatsAppCloudClient


class _Client(WhatsAppCloudClient):
    def __init__(self):
        super().__init__()
        self.template_calls = 0

    def send_template_message(self, *args, **kwargs):
        self.template_calls += 1
        return {"messages": [{"id": "wamid.outbound-1"}]}


class CrmWhatsAppActionTests(Integration2ATestCase):
    def configure_whatsapp(self):
        response = self.client.post(
            "/api/v1/integrations/whatsapp/config",
            json={
                "phone_number_id": "phone-number-1",
                "business_account_id": "waba-1",
                "display_phone_number": "+573001112233",
                "default_language": "es",
                "status": "active",
                "access_token": "EA_secret_token_12345678901234567890",
            },
        )
        self.assertEqual(response.status_code, 200)

    def seed_synced_template(self):
        with SessionLocal() as db:
            template = TenantWhatsAppTemplate(
                tenant_id=self.tenant.id,
                template_key="appointment_reminder",
                provider_template_name="appointment_reminder",
                name="appointment_reminder",
                category="utility",
                language="es",
                body="Hola {{1}}, cita {{2}}",
                variables_json={
                    "parameters": [{"key": "1", "label": "Variable 1"}, {"key": "2", "label": "Variable 2"}],
                    "meta_status": "APPROVED",
                    "source": "meta_sync",
                },
                status="active",
            )
            db.add(template)
            db.commit()

    def test_whatsapp_action_requires_contact_phone(self):
        self.configure_whatsapp()
        lead_id, _ = self.seed_lead()
        with SessionLocal() as db:
            message = db.get(CrmWhatsAppMessage, "missing")
            lead = db.scalar(select(CrmWhatsAppMessage).where(CrmWhatsAppMessage.lead_id == lead_id))
            self.assertIsNone(message)
            self.assertIsNone(lead)
        with SessionLocal() as db:
            from app.models.crm import CrmContact, CrmLead

            lead = db.get(CrmLead, lead_id)
            contact = db.get(CrmContact, lead.contact_id)
            contact.phone = None
            db.commit()

        response = self.client.post(f"/api/v1/crm/leads/{lead_id}/actions/whatsapp", json={"template_key": "lead_follow_up"})

        self.assertEqual(response.status_code, 422)

    def test_whatsapp_action_preview_does_not_call_meta_or_persist_message(self):
        self.configure_whatsapp()
        lead_id, _ = self.seed_lead()
        client = _Client()
        with SessionLocal() as db:
            from app.services.whatsapp_message_service import WhatsAppMessageService

            result = WhatsAppMessageService(db, client=client).preview_lead_whatsapp(
                self.tenant.id,
                lead_id,
                __import__("app.schemas.crm", fromlist=["WhatsAppActionRequest"]).WhatsAppActionRequest(
                    template_key="lead_follow_up",
                    preview_only=True,
                ),
            )

        self.assertEqual(result.status, "preview")
        self.assertEqual(client.template_calls, 0)
        with SessionLocal() as db:
            count = db.scalar(select(func.count()).select_from(CrmWhatsAppMessage))
        self.assertEqual(count, 0)

    def test_whatsapp_action_sends_persists_activity_and_event(self):
        self.configure_whatsapp()
        lead_id, _ = self.seed_lead()
        client = _Client()
        with SessionLocal() as db:
            from app.schemas.crm import WhatsAppActionRequest
            from app.services.whatsapp_message_service import WhatsAppMessageService

            result = WhatsAppMessageService(db, client=client).send_lead_whatsapp(
                self.tenant.id,
                lead_id,
                WhatsAppActionRequest(template_key="lead_follow_up"),
            )

        self.assertEqual(result.status, "sent")
        with SessionLocal() as db:
            message = db.scalar(select(CrmWhatsAppMessage).where(CrmWhatsAppMessage.lead_id == lead_id))
            activity = db.scalar(select(CrmActivity).where(CrmActivity.lead_id == lead_id, CrmActivity.activity_type == "whatsapp_template_sent"))
            event = db.scalar(select(TenantIntegrationEvent).where(TenantIntegrationEvent.event_type == "whatsapp_message_sent"))
        self.assertIsNotNone(message)
        self.assertEqual(message.provider_message_id, "wamid.outbound-1")
        self.assertIsNotNone(activity)
        self.assertIsNotNone(event)

    def test_whatsapp_action_does_not_cross_tenant(self):
        self.configure_whatsapp()
        other_tenant, _ = self._seed_tenant_user(slug="tenant-b", email="b@example.com")
        other_lead_id, _ = self.seed_lead(tenant_id=other_tenant.id)

        response = self.client.post(f"/api/v1/crm/leads/{other_lead_id}/actions/whatsapp", json={"template_key": "lead_follow_up"})

        self.assertEqual(response.status_code, 404)

    def test_send_whatsapp_test_message_sends_persists_without_lead_and_masks_phone(self):
        self.configure_whatsapp()
        self.seed_synced_template()
        with SessionLocal() as db:
            from app.services.whatsapp_message_service import WhatsAppMessageService

            result = WhatsAppMessageService(db, client=_Client()).send_test_template_message(
                self.tenant.id,
                WhatsAppTestMessageRequest(
                    to_phone="+573001112233",
                    template_key="appointment_reminder",
                    variables={"1": "Aly", "2": "mañana a las 10 AM"},
                ),
            )

        self.assertEqual(result.status, "sent")
        self.assertEqual(result.to_phone_masked, "***2233")
        with SessionLocal() as db:
            message = db.get(CrmWhatsAppMessage, result.whatsapp_message_id)
            activity_count = db.scalar(select(func.count()).select_from(CrmActivity))
            event = db.scalar(select(TenantIntegrationEvent).where(TenantIntegrationEvent.event_type == "whatsapp_test_message"))
        self.assertIsNone(message.lead_id)
        self.assertIsNone(message.contact_id)
        self.assertTrue(message.metadata_json["test_message"])
        self.assertEqual(activity_count, 0)
        self.assertIsNotNone(event)

    def test_send_whatsapp_test_message_requires_template_variables(self):
        self.configure_whatsapp()
        self.seed_synced_template()
        with SessionLocal() as db:
            from app.services.whatsapp_message_service import WhatsAppMessageService

            with self.assertRaisesRegex(ValueError, "Missing template variables: 1, 2"):
                WhatsAppMessageService(db, client=_Client()).send_test_template_message(
                    self.tenant.id,
                    WhatsAppTestMessageRequest(to_phone="573001112233", template_key="appointment_reminder"),
                )

    def test_send_whatsapp_test_message_rejects_unapproved_template(self):
        self.configure_whatsapp()
        with SessionLocal() as db:
            from app.services.whatsapp_message_service import WhatsAppMessageService

            with self.assertRaisesRegex(ValueError, "approved by Meta"):
                WhatsAppMessageService(db, client=_Client()).send_test_template_message(
                    self.tenant.id,
                    WhatsAppTestMessageRequest(to_phone="573001112233", template_key="lead_follow_up"),
                )


if __name__ == "__main__":
    import unittest

    unittest.main()
