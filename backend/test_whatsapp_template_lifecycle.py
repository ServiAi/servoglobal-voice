from __future__ import annotations

from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.models.crm import CrmWhatsAppMessage
from app.models.integrations import TenantIntegrationEvent, TenantWhatsAppTemplate
from app.services.whatsapp_client import WhatsAppCloudClient
from app.services.whatsapp_config_service import WhatsAppConfigService
from app.services.whatsapp_template_service import WhatsAppTemplateService


def _whatsapp_config_payload(**overrides):
    return {
        "phone_number_id": "phone-number-1",
        "business_account_id": "waba-1",
        "display_phone_number": "+573001112233",
        "default_language": "es",
        "status": "active",
        "access_token": "EA_secret_token_12345678901234567890",
        **overrides,
    }


def _create_template_payload(**overrides):
    return {
        "template_key": "cita_confirmada",
        "name": "Cita confirmada",
        "category": "utility",
        "language": "es",
        "header_text": None,
        "body": "Hola {{nombre}}, tu cita es el {{fecha_cita}}.",
        "footer_text": "ServiGlobal AI",
        "buttons": [],
        **overrides,
    }


class WhatsAppTemplateDraftCrudTests(Integration2ATestCase):
    def test_create_draft_defaults_to_named_tenant_authored(self):
        response = self.client.post("/api/v1/integrations/whatsapp/templates", json=_create_template_payload())

        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["status"], "draft")
        self.assertEqual(body["source"], "tenant_authored")
        self.assertEqual(body["parameter_format"], "NAMED")
        self.assertEqual(sorted(body["variables"]["parameters"], key=lambda item: item["key"]), [
            {"key": "fecha_cita", "label": "Variable fecha_cita"},
            {"key": "nombre", "label": "Variable nombre"},
        ])

    def test_create_draft_duplicate_template_key_returns_422(self):
        self.client.post("/api/v1/integrations/whatsapp/templates", json=_create_template_payload())
        response = self.client.post("/api/v1/integrations/whatsapp/templates", json=_create_template_payload())

        self.assertEqual(response.status_code, 422)
        self.assertIn("already exists", response.json()["detail"])

    def test_update_draft_recomputes_variables(self):
        created = self.client.post("/api/v1/integrations/whatsapp/templates", json=_create_template_payload()).json()

        response = self.client.patch(
            f"/api/v1/integrations/whatsapp/templates/{created['id']}",
            json={"body": "Hola {{nombre_cliente}}, confirmamos tu reserva."},
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["variables"]["parameters"], [{"key": "nombre_cliente", "label": "Variable nombre_cliente"}])

    def test_update_non_draft_template_returns_422(self):
        created = self.client.post("/api/v1/integrations/whatsapp/templates", json=_create_template_payload()).json()
        with SessionLocal() as db:
            template = db.get(TenantWhatsAppTemplate, created["id"])
            template.status = "approved"
            db.commit()

        response = self.client.patch(
            f"/api/v1/integrations/whatsapp/templates/{created['id']}",
            json={"body": "Nuevo texto"},
        )

        self.assertEqual(response.status_code, 422)

    def test_delete_pure_draft_removes_row(self):
        created = self.client.post("/api/v1/integrations/whatsapp/templates", json=_create_template_payload()).json()

        response = self.client.delete(f"/api/v1/integrations/whatsapp/templates/{created['id']}")

        self.assertEqual(response.status_code, 204)
        with SessionLocal() as db:
            self.assertIsNone(db.get(TenantWhatsAppTemplate, created["id"]))

    def test_delete_referenced_template_returns_422(self):
        created = self.client.post("/api/v1/integrations/whatsapp/templates", json=_create_template_payload()).json()
        with SessionLocal() as db:
            db.add(
                CrmWhatsAppMessage(
                    tenant_id=self.tenant.id,
                    template_id=created["id"],
                    template_key=created["template_key"],
                    direction="outbound",
                    to_phone="+573001112233",
                    status="sent",
                )
            )
            db.commit()

        response = self.client.delete(f"/api/v1/integrations/whatsapp/templates/{created['id']}")

        self.assertEqual(response.status_code, 422)
        with SessionLocal() as db:
            self.assertIsNotNone(db.get(TenantWhatsAppTemplate, created["id"]))

    def test_delete_non_draft_disables_instead_of_removing(self):
        created = self.client.post("/api/v1/integrations/whatsapp/templates", json=_create_template_payload()).json()
        with SessionLocal() as db:
            template = db.get(TenantWhatsAppTemplate, created["id"])
            template.status = "approved"
            db.commit()

        response = self.client.delete(f"/api/v1/integrations/whatsapp/templates/{created['id']}")

        self.assertEqual(response.status_code, 204)
        with SessionLocal() as db:
            template = db.get(TenantWhatsAppTemplate, created["id"])
            self.assertEqual(template.status, "disabled")

    def test_preview_renders_sample_values(self):
        created = self.client.post("/api/v1/integrations/whatsapp/templates", json=_create_template_payload()).json()

        response = self.client.get(f"/api/v1/integrations/whatsapp/templates/{created['id']}/preview")

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIn("[nombre]", body["body"])
        self.assertIn("[fecha_cita]", body["body"])


class WhatsAppTemplateSubmitAndSyncTests(Integration2ATestCase):
    def setUp(self):
        super().setUp()
        self.client.post("/api/v1/integrations/whatsapp/config", json=_whatsapp_config_payload())
        self.template_id = self.client.post(
            "/api/v1/integrations/whatsapp/templates", json=_create_template_payload()
        ).json()["id"]

    def test_submit_moves_draft_to_pending_and_records_event(self):
        class _Client(WhatsAppCloudClient):
            def create_message_template(self, config, *, waba_id, name, category, language, components, parameter_format="NAMED"):
                return {"id": "meta-tpl-1", "status": "PENDING"}

        with SessionLocal() as db:
            result = WhatsAppConfigService(db, client=_Client()).submit_template(self.tenant.id, self.template_id)

        self.assertEqual(result.status, "success")
        self.assertEqual(result.meta_status, "PENDING")
        self.assertEqual(result.provider_template_id, "meta-tpl-1")
        with SessionLocal() as db:
            template = db.get(TenantWhatsAppTemplate, self.template_id)
            self.assertEqual(template.status, "pending")
            self.assertEqual(template.provider_template_id, "meta-tpl-1")
            event = db.scalar(
                select(TenantIntegrationEvent).where(TenantIntegrationEvent.event_type == "whatsapp_template_submit")
            )
        self.assertIsNotNone(event)

    def test_submit_non_draft_template_raises(self):
        with SessionLocal() as db:
            template = db.get(TenantWhatsAppTemplate, self.template_id)
            template.status = "approved"
            db.commit()

        with SessionLocal() as db:
            with self.assertRaises(ValueError):
                WhatsAppConfigService(db).submit_template(self.tenant.id, self.template_id)

    def test_sync_status_approved_clears_rejection_reason(self):
        class _CreateClient(WhatsAppCloudClient):
            def create_message_template(self, config, *, waba_id, name, category, language, components, parameter_format="NAMED"):
                return {"id": "meta-tpl-2", "status": "PENDING"}

        class _StatusClient(WhatsAppCloudClient):
            def get_message_template_status(self, config, *, provider_template_id):
                return {"status": "APPROVED", "name": "x", "id": provider_template_id, "category": "UTILITY", "language": "es", "rejected_reason": None}

        with SessionLocal() as db:
            WhatsAppConfigService(db, client=_CreateClient()).submit_template(self.tenant.id, self.template_id)
        with SessionLocal() as db:
            result = WhatsAppConfigService(db, client=_StatusClient()).sync_template_status(self.tenant.id, self.template_id)

        self.assertEqual(result.status, "success")
        self.assertEqual(result.meta_status, "APPROVED")
        with SessionLocal() as db:
            template = db.get(TenantWhatsAppTemplate, self.template_id)
            self.assertEqual(template.status, "approved")
            self.assertIsNone(template.rejection_reason)

    def test_sync_status_rejected_records_sanitized_reason(self):
        class _CreateClient(WhatsAppCloudClient):
            def create_message_template(self, config, *, waba_id, name, category, language, components, parameter_format="NAMED"):
                return {"id": "meta-tpl-3", "status": "PENDING"}

        class _StatusClient(WhatsAppCloudClient):
            def get_message_template_status(self, config, *, provider_template_id):
                return {
                    "status": "REJECTED",
                    "name": "x",
                    "id": provider_template_id,
                    "category": "UTILITY",
                    "language": "es",
                    "rejected_reason": "Contains disallowed content",
                }

        with SessionLocal() as db:
            WhatsAppConfigService(db, client=_CreateClient()).submit_template(self.tenant.id, self.template_id)
        with SessionLocal() as db:
            result = WhatsAppConfigService(db, client=_StatusClient()).sync_template_status(self.tenant.id, self.template_id)

        self.assertEqual(result.status, "success")
        self.assertEqual(result.meta_status, "REJECTED")
        with SessionLocal() as db:
            template = db.get(TenantWhatsAppTemplate, self.template_id)
            self.assertEqual(template.status, "rejected")
            self.assertEqual(template.rejection_reason, "Contains disallowed content")


class WhatsAppDefaultTemplateBackfillBehaviorTests(Integration2ATestCase):
    """Covers the lifecycle invariants the 202608310001 migration backfill establishes:
    default seed templates start as unsent drafts, meta_sync rows land as approved."""

    def test_ensure_default_templates_creates_drafts(self):
        with SessionLocal() as db:
            WhatsAppTemplateService(db).ensure_default_templates(self.tenant.id)
            templates = db.scalars(
                select(TenantWhatsAppTemplate).where(TenantWhatsAppTemplate.tenant_id == self.tenant.id)
            ).all()

        self.assertEqual(len(templates), 2)
        for template in templates:
            self.assertEqual(template.status, "draft")
            self.assertEqual(template.source, "tenant_authored")
            self.assertEqual(template.parameter_format, "NAMED")

    def test_sync_approved_templates_from_meta_lands_as_approved(self):
        with SessionLocal() as db:
            WhatsAppTemplateService(db).sync_approved_templates_from_meta(
                self.tenant.id,
                [
                    {
                        "name": "welcome_message",
                        "status": "APPROVED",
                        "language": "es",
                        "category": "UTILITY",
                        "components": [{"type": "BODY", "text": "Hola {{1}}"}],
                    }
                ],
            )
            template = db.scalar(
                select(TenantWhatsAppTemplate).where(TenantWhatsAppTemplate.template_key == "welcome_message")
            )

        self.assertEqual(template.status, "approved")
        self.assertEqual(template.meta_status, "APPROVED")
        self.assertEqual(template.source, "meta_sync")
        self.assertEqual(template.parameter_format, "POSITIONAL")


if __name__ == "__main__":
    import unittest

    unittest.main()
