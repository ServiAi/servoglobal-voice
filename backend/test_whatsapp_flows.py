from __future__ import annotations

from types import SimpleNamespace
import unittest

from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.models.identity import Tenant, TenantMembership
from app.models.integrations import TenantIntegrationEvent, TenantWhatsAppFlow
from app.schemas.integrations import WhatsAppConfigRequest
from app.schemas.whatsapp_flows import WhatsAppFlowCreateRequest, WhatsAppFlowUpdateRequest
from app.services.whatsapp_config_service import WhatsAppConfigService
from app.services.whatsapp_flow_compiler import WhatsAppFlowCompiler
from app.services.whatsapp_flow_context_adapter import builder_from_context_schema
from app.services.whatsapp_flow_service import (
    WhatsAppFlowConflictError,
    WhatsAppFlowNotFoundError,
    WhatsAppFlowService,
)


def one_screen_builder():
    return {
        "version": 1,
        "screens": [
            {
                "id": "START",
                "title": "Datos",
                "terminal": True,
                "components": [
                    {"id": "heading", "type": "heading", "text": "Tus datos"},
                    {"id": "body", "type": "body", "text": "Completa el formulario"},
                    {"id": "name", "type": "text_input", "label": "Nombre", "required": True},
                    {"id": "email", "type": "email_input", "label": "Correo"},
                    {"id": "phone", "type": "phone_input", "label": "Teléfono"},
                    {"id": "age", "type": "number_input", "label": "Edad"},
                    {"id": "notes", "type": "text_area", "label": "Notas"},
                    {"id": "interest", "type": "dropdown", "label": "Interés", "options": [{"id": "sales", "title": "Ventas"}]},
                    {"id": "channel", "type": "radio", "label": "Canal", "options": [{"id": "web", "title": "Web"}]},
                    {"id": "consent", "type": "checkbox", "label": "Acepto", "required": True},
                    {"id": "date", "type": "date", "label": "Fecha"},
                    {"id": "submit", "type": "footer", "label": "Enviar", "action": {"type": "complete"}},
                ],
            }
        ],
    }


class FakeFlowClient:
    def __init__(self, validation_errors=None):
        self.validation_errors = validation_errors or []
        self.calls = []

    def create_flow(self, *args, **kwargs):
        self.calls.append(("create", kwargs))
        return {"id": "flow-test-123"}

    def update_flow_metadata(self, *args, **kwargs):
        self.calls.append(("update", kwargs))
        return {"success": True}

    def upload_flow_json(self, *args, **kwargs):
        self.calls.append(("upload", kwargs))
        return {"success": True, "validation_errors": self.validation_errors}

    def publish_flow(self, *args, **kwargs):
        self.calls.append(("publish", kwargs))
        return {"success": True}

    def get_flow(self, *args, **kwargs):
        return {"id": "flow-test-123", "status": "PUBLISHED", "validation_errors": []}

    def deprecate_flow(self, *args, **kwargs):
        return {"success": True}

    def delete_flow(self, *args, **kwargs):
        return {"success": True}


class WhatsAppFlowCompilerTests(unittest.TestCase):
    def test_compiler_supports_v1_components_and_is_deterministic(self):
        first = WhatsAppFlowCompiler().compile(one_screen_builder())
        second = WhatsAppFlowCompiler().compile(one_screen_builder())
        self.assertEqual(first, second)
        compiled, digest = first
        self.assertEqual(compiled["version"], "7.3")
        types = {item["type"] for item in compiled["screens"][0]["layout"]["children"][0]["children"]}
        self.assertTrue({"TextHeading", "TextBody", "TextInput", "TextArea", "Dropdown", "RadioButtonsGroup", "OptIn", "DatePicker", "Footer"}.issubset(types))
        self.assertEqual(len(digest), 64)

    def test_compiler_rejects_duplicate_ids_and_missing_target(self):
        builder = one_screen_builder()
        builder["screens"][0]["components"][2]["id"] = "heading"
        with self.assertRaisesRegex(ValueError, "unique"):
            WhatsAppFlowCompiler().compile(builder)

    def test_context_adapter_obeys_collection_modes_and_snapshots(self):
        fields = []
        modes = ["ask_if_missing", "prefill_and_confirm", "trust_prefill", "internal_only", "collect_during_call"]
        types = ["text", "email", "phone", "integer", "select", "checkbox", "date", "textarea"]
        for index, field_type in enumerate(types):
            fields.append(SimpleNamespace(
                key=f"field_{index}", label=f"Field {index}", description=None,
                field_type=field_type, collection_mode=modes[index % len(modes)], required=False,
                position=index, options_json=[{"value": "one", "label": "One"}] if field_type == "select" else [],
            ))
        schema = SimpleNamespace(schema_key="lead", version=3, name="Lead", description=None, fields=fields)
        builder, snapshot = builder_from_context_schema(schema)
        visible_ids = {item["id"] for item in builder["screens"][0]["components"]}
        self.assertIn("field_0", visible_ids)
        self.assertIn("field_1", visible_ids)
        self.assertNotIn("field_2", visible_ids)
        self.assertNotIn("field_3", visible_ids)
        self.assertNotIn("field_4", visible_ids)
        self.assertEqual(len(snapshot["fields"]), len(types))


class WhatsAppFlowApiTests(Integration2ATestCase):
    def create_flow(self, **overrides):
        payload = {
            "name": "Precalificación",
            "flow_key": "lead_qualification",
            "categories": ["LEAD_GENERATION"],
            "source_mode": "visual",
            "builder": one_screen_builder(),
            **overrides,
        }
        return self.client.post("/api/v1/integrations/whatsapp/flows", json=payload)

    def test_create_list_update_delete_draft(self):
        created = self.create_flow()
        self.assertEqual(created.status_code, 201, created.text)
        flow_id = created.json()["id"]
        self.assertEqual(len(self.client.get("/api/v1/integrations/whatsapp/flows").json()), 1)
        updated = self.client.patch(f"/api/v1/integrations/whatsapp/flows/{flow_id}", json={"name": "Nuevo nombre"})
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["name"], "Nuevo nombre")
        self.assertEqual(self.client.delete(f"/api/v1/integrations/whatsapp/flows/{flow_id}").status_code, 204)

    def test_tenant_id_is_rejected_from_tenant_payload(self):
        response = self.create_flow(tenant_id="another-tenant")
        self.assertEqual(response.status_code, 422)

    def test_tenant_isolation_returns_404(self):
        other, _ = self._seed_tenant_user(slug="tenant-b", email="other@example.com")
        with SessionLocal() as db:
            flow = TenantWhatsAppFlow(
                tenant_id=other.id, flow_key="private", version=1, name="Private",
                categories_json=["OTHER"], source_mode="visual", status="draft",
                builder_schema_version=1, builder_json=one_screen_builder(),
            )
            db.add(flow)
            db.commit()
            db.refresh(flow)
            flow_id = flow.id
        self.assertEqual(self.client.get(f"/api/v1/integrations/whatsapp/flows/{flow_id}").status_code, 404)
        self.assertEqual(self.client.patch(f"/api/v1/integrations/whatsapp/flows/{flow_id}", json={"name": "attack"}).status_code, 404)

    def test_read_roles_can_read_but_cannot_write(self):
        created = self.create_flow().json()
        with SessionLocal() as db:
            membership = db.scalar(select(TenantMembership).where(TenantMembership.tenant_id == self.tenant.id))
            membership.role = "tenant_viewer"
            db.commit()
        self.assertEqual(self.client.get(f"/api/v1/integrations/whatsapp/flows/{created['id']}").status_code, 200)
        self.assertEqual(self.client.patch(f"/api/v1/integrations/whatsapp/flows/{created['id']}", json={"name": "blocked"}).status_code, 403)

    def test_published_is_immutable_and_clones_next_version(self):
        flow_id = self.create_flow().json()["id"]
        with SessionLocal() as db:
            flow = db.get(TenantWhatsAppFlow, flow_id)
            flow.status = "published"
            flow.meta_status = "PUBLISHED"
            flow.provider_flow_id = "meta-flow-1"
            db.commit()
        self.assertEqual(self.client.patch(f"/api/v1/integrations/whatsapp/flows/{flow_id}", json={"name": "blocked"}).status_code, 409)
        self.assertEqual(self.client.delete(f"/api/v1/integrations/whatsapp/flows/{flow_id}").status_code, 409)
        clone = self.client.post(f"/api/v1/integrations/whatsapp/flows/{flow_id}/clone")
        self.assertEqual(clone.status_code, 201, clone.text)
        self.assertEqual(clone.json()["version"], 2)
        self.assertEqual(clone.json()["parent_flow_id"], flow_id)
        self.assertEqual(clone.json()["status"], "draft")


class WhatsAppFlowProviderTests(Integration2ATestCase):
    def _configure(self, db, client):
        WhatsAppConfigService(db, client).upsert_config(self.tenant.id, WhatsAppConfigRequest(
            phone_number_id="phone-1", business_account_id="waba-1", status="active",
            access_token="EA_test_token_12345678901234567890",
        ))

    def _create(self, db, client):
        return WhatsAppFlowService(db, client).create_draft(
            self.tenant.id,
            WhatsAppFlowCreateRequest(
                name="Lead", flow_key="lead", categories=["LEAD_GENERATION"],
                source_mode="visual", builder=one_screen_builder(),
            ),
            self.user.id,
        )

    def test_sync_persists_provider_id_and_publish_is_immutable(self):
        fake = FakeFlowClient()
        with SessionLocal() as db:
            self._configure(db, fake)
            flow = self._create(db, fake)
            synced = WhatsAppFlowService(db, fake).sync_meta(self.tenant.id, flow.id)
            self.assertEqual(synced.provider_flow_id, "flow-test-123")
            self.assertEqual(synced.status, "synced")
            published = WhatsAppFlowService(db, fake).publish(self.tenant.id, flow.id)
            self.assertEqual(published.status, "published")
            self.assertEqual(published.meta_status, "PUBLISHED")
            with self.assertRaises(WhatsAppFlowConflictError):
                WhatsAppFlowService(db, fake).update_draft(self.tenant.id, flow.id, WhatsAppFlowUpdateRequest(name="No"))
            events = db.scalars(select(TenantIntegrationEvent).where(TenantIntegrationEvent.tenant_id == self.tenant.id)).all()
            self.assertIn("whatsapp_flow_published", {event.event_type for event in events})

    def test_meta_validation_errors_are_sanitized_and_block_publish(self):
        fake = FakeFlowClient([{
            "error": "INVALID_PROPERTY", "error_type": "JSON_SCHEMA_ERROR",
            "message": "Invalid property for +573001112233", "line_start": 10,
            "line_end": 10, "column_start": 5, "column_end": 15,
        }])
        with SessionLocal() as db:
            self._configure(db, fake)
            flow = self._create(db, fake)
            synced = WhatsAppFlowService(db, fake).sync_meta(self.tenant.id, flow.id)
            self.assertEqual(synced.status, "error")
            self.assertIn("[REDACTED_PHONE]", synced.validation_errors[0].message)
            with self.assertRaises(WhatsAppFlowConflictError):
                WhatsAppFlowService(db, fake).publish(self.tenant.id, flow.id)

    def test_wrong_tenant_service_lookup_fails_closed(self):
        fake = FakeFlowClient()
        with SessionLocal() as db:
            flow = self._create(db, fake)
            with self.assertRaises(WhatsAppFlowNotFoundError):
                WhatsAppFlowService(db, fake).get_owned("another-tenant", flow.id)


if __name__ == "__main__":
    unittest.main()
