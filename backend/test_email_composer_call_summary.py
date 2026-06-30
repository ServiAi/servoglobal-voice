from __future__ import annotations

import os
from pathlib import Path
import unittest

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")
os.environ["SERVIAI_TEST_SECRET_FALLBACK"] = "1"
TEST_DB_PATH = Path("serviai_email_composer_call_summary_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"
os.environ["EMAIL_ASSETS_STORAGE_PATH"] = "storage/test-call-summary"

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.auth.deps import AuthContext, get_current_auth_context
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.crm import CrmActivity, CrmContact, CrmLead
from app.models.identity import Tenant, TenantMembership, User
from app.services.crm_pipeline_service import CrmPipelineService
from app.services.email_config_service import EmailConfigService
from app.services.integration_service import IntegrationService


class EmailComposerCallSummaryTests(unittest.TestCase):
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
                short_summary=None,
                summary=None,
            )
            db.add(lead)
            db.commit()
            db.refresh(lead)
            self.lead_id = lead.id
            self.contact_id = contact.id
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

    def test_get_call_summary_from_latest_activity(self):
        with SessionLocal() as db:
            db.add(
                CrmActivity(
                    tenant_id=self.tenant_id,
                    lead_id=self.lead_id,
                    contact_id=self.contact_id,
                    activity_type="call_ended",
                    title="Llamada finalizada",
                    payload_json={
                        "event": "call.ended",
                        "call": {
                            "summary": "La empresa necesita automatizar soporte.",
                            "shortSummary": "Necesita soporte automatizado.",
                            "durationSeconds": 180,
                        },
                    },
                )
            )
            db.commit()

        response = self.client.get(f"/api/v1/crm/leads/{self.lead_id}/call-summary")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "available")
        self.assertEqual(payload["source"], "crm_activity")
        self.assertEqual(payload["duration_seconds"], 180)
        self.assertIn("automatizar soporte", payload["summary"])

    def test_get_call_summary_falls_back_to_lead_summary(self):
        with SessionLocal() as db:
            lead = db.get(CrmLead, self.lead_id)
            lead.summary = "Resumen guardado en el lead."
            lead.short_summary = "Resumen corto."
            db.commit()

        response = self.client.get(f"/api/v1/crm/leads/{self.lead_id}/call-summary")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "crm_lead")
        self.assertEqual(response.json()["short_summary"], "Resumen corto.")

    def test_get_call_summary_returns_not_found_when_missing(self):
        response = self.client.get(f"/api/v1/crm/leads/{self.lead_id}/call-summary")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "not_found")
        self.assertIsNone(response.json()["summary"])

    def test_call_summary_variable_renders_in_email(self):
        with SessionLocal() as db:
            lead = db.get(CrmLead, self.lead_id)
            lead.summary = "Resumen completo para enviar al cliente."
            lead.short_summary = "Resumen corto."
            db.commit()

        response = self.client.post(
            f"/api/v1/crm/leads/{self.lead_id}/actions/email",
            json={"content": "Resumen: {{call_summary}}", "preview_only": True},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Resumen completo para enviar", response.json()["preview"]["text"])

    def test_call_summary_short_variable_renders_in_email(self):
        with SessionLocal() as db:
            lead = db.get(CrmLead, self.lead_id)
            lead.summary = "Resumen completo largo."
            lead.short_summary = "Resumen corto comercial."
            db.commit()

        response = self.client.post(
            f"/api/v1/crm/leads/{self.lead_id}/actions/email",
            json={"content": "Resumen: {{call_summary_short}}", "preview_only": True},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Resumen corto comercial.", response.json()["preview"]["text"])


if __name__ == "__main__":
    unittest.main()
