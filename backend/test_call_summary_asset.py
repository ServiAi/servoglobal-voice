from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")
os.environ["SERVIAI_TEST_SECRET_FALLBACK"] = "1"
TEST_DB_PATH = Path("serviai_call_summary_asset_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"
os.environ["EMAIL_ASSETS_STORAGE_PATH"] = "storage/test-call-summary-assets"

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.auth.deps import AuthContext, get_current_auth_context
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.crm import CrmActivity, CrmContact, CrmLead
from app.models.identity import Tenant, TenantMembership, User
from app.models.integrations import TenantEmailAsset
from app.services.crm_pipeline_service import CrmPipelineService
from app.services.email_config_service import EmailConfigService
from app.services.integration_service import IntegrationService
from app.services.storage_service import StorageService


class CallSummaryAssetTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        TEST_DB_PATH.unlink(missing_ok=True)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        app.dependency_overrides.clear()
        self.client = TestClient(app)
        with SessionLocal() as db:
            self.tenant = Tenant(name="Tenant A", slug="tenant-a")
            self.user = User(email="admin@example.com", name="Admin", status="active")
            db.add_all([self.tenant, self.user])
            db.commit()
            db.refresh(self.tenant)
            db.refresh(self.user)
            self.tenant_id = self.tenant.id
            self.user_id = self.user.id
            db.add(TenantMembership(tenant_id=self.tenant_id, user_id=self.user_id, role="tenant_admin", status="active"))
            stage = CrmPipelineService(db).ensure_default_pipeline(self.tenant_id)[0]
            contact = CrmContact(tenant_id=self.tenant_id, name="Ana", email="ana@example.com", company="ACME")
            db.add(contact)
            db.commit()
            db.refresh(contact)
            lead = CrmLead(
                tenant_id=self.tenant_id,
                contact_id=contact.id,
                current_stage_id=stage.id,
                interest="Automatizacion",
                use_case="Atencion comercial",
                pain_point="Pierde llamadas",
                summary="Resumen sensible de la llamada comercial.",
                short_summary="Resumen corto.",
            )
            db.add(lead)
            db.commit()
            db.refresh(lead)
            self.lead_id = lead.id
            self._configure_resend(db)
        app.dependency_overrides[get_current_auth_context] = self._auth_context_override

    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    async def _auth_context_override(self):
        with SessionLocal() as db:
            tenant = db.get(Tenant, self.tenant_id)
            user = db.get(User, self.user_id)
            membership = db.scalar(select(TenantMembership).where(TenantMembership.tenant_id == tenant.id))
            return AuthContext(user=user, tenant=tenant, membership=membership)

    def _configure_resend(self, db):
        EmailConfigService(db).upsert_resend_config(
            tenant_id=self.tenant_id,
            sender_name="ServiGlobal IA",
            sender_email="comercial@mail.serviglobal-ia.com",
            reply_to=None,
            default_domain="mail.serviglobal-ia.com",
            status="active",
        )
        IntegrationService(db).upsert_resend(
            tenant_id=self.tenant_id,
            display_name="Resend",
            config={"sender_email": "comercial@mail.serviglobal-ia.com"},
            api_key="re_secret_test",
        )

    def _create_asset(self, file_format: str = "md") -> dict:
        response = self.client.post(
            f"/api/v1/crm/leads/{self.lead_id}/call-summary/asset",
            json={"format": file_format},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_call_summary_asset_md_is_created(self):
        payload = self._create_asset("md")

        self.assertTrue(payload["filename"].endswith(".md"))
        self.assertEqual(payload["mime_type"], "text/markdown")
        with SessionLocal() as db:
            asset = db.get(TenantEmailAsset, payload["asset_id"])
            content = StorageService().read_bytes(asset.storage_key).decode("utf-8")
        self.assertIn("# Resumen de llamada", content)
        self.assertIn("Resumen sensible", content)

    def test_call_summary_asset_txt_is_created(self):
        payload = self._create_asset("txt")

        self.assertTrue(payload["filename"].endswith(".txt"))
        self.assertEqual(payload["mime_type"], "text/plain")

    def test_call_summary_asset_uses_storage_service(self):
        payload = self._create_asset("md")

        with SessionLocal() as db:
            asset = db.get(TenantEmailAsset, payload["asset_id"])
        self.assertTrue(asset.storage_key.startswith(f"tenants/{self.tenant_id}/email-assets/{asset.id}/"))
        self.assertGreater(len(StorageService().read_bytes(asset.storage_key)), 0)

    def test_call_summary_asset_rejects_cross_tenant_lead(self):
        with SessionLocal() as db:
            other = Tenant(name="Tenant B", slug="tenant-b")
            db.add(other)
            db.commit()
            db.refresh(other)
            stage = CrmPipelineService(db).ensure_default_pipeline(other.id)[0]
            contact = CrmContact(tenant_id=other.id, name="Beto", email="beto@example.com")
            db.add(contact)
            db.commit()
            db.refresh(contact)
            lead = CrmLead(tenant_id=other.id, contact_id=contact.id, current_stage_id=stage.id, summary="Otro resumen")
            db.add(lead)
            db.commit()
            db.refresh(lead)
            other_lead_id = lead.id

        response = self.client.post(f"/api/v1/crm/leads/{other_lead_id}/call-summary/asset", json={"format": "md"})

        self.assertEqual(response.status_code, 404)

    def test_call_summary_asset_does_not_log_summary_content(self):
        payload = self._create_asset("md")

        with SessionLocal() as db:
            activity = db.scalar(
                select(CrmActivity).where(
                    CrmActivity.tenant_id == self.tenant_id,
                    CrmActivity.activity_type == "call_summary_attached_to_email",
                )
            )
        self.assertEqual(activity.payload_json, {"email_asset_id": payload["asset_id"], "format": "md"})
        self.assertNotIn("Resumen sensible", str(activity.payload_json))
        self.assertIsNone(activity.description)

    def test_email_send_with_call_summary_asset_succeeds(self):
        payload = self._create_asset("md")
        with patch("app.services.email_send_service.ResendService") as service_cls:
            service_cls.return_value.send_email.return_value = "email_1"
            response = self.client.post(
                f"/api/v1/crm/leads/{self.lead_id}/actions/email",
                json={"content": "Hola {{contact_name}}", "asset_ids": [payload["asset_id"]]},
            )

        self.assertEqual(response.status_code, 200)
        service_cls.return_value.send_email.assert_called_once()


if __name__ == "__main__":
    unittest.main()
