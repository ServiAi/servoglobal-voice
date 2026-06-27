from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")
os.environ["SERVIAI_TEST_SECRET_FALLBACK"] = "1"
TEST_DB_PATH = Path("serviai_crm_email_action_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.auth.deps import AuthContext, get_current_auth_context
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.crm import CrmActivity, CrmContact, CrmLead
from app.models.identity import Tenant, TenantMembership, User
from app.models.integrations import TenantEmailSend
from app.services.crm_pipeline_service import CrmPipelineService
from app.services.email_config_service import EmailConfigService
from app.services.integration_service import IntegrationService
from app.services.resend_service import ResendServiceError


class CrmEmailActionTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        TEST_DB_PATH.unlink(missing_ok=True)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        app.dependency_overrides.clear()
        self.client = TestClient(app)
        self.tenant, self.user = self._seed_tenant_user("tenant-a", "admin-a@example.com")
        self.other_tenant, _ = self._seed_tenant_user("tenant-b", "admin-b@example.com")
        app.dependency_overrides[get_current_auth_context] = self._auth_context_override

    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def _seed_tenant_user(self, slug: str, email: str):
        with SessionLocal() as db:
            tenant = Tenant(name=slug, slug=slug)
            user = User(email=email, name=slug, status="active")
            db.add_all([tenant, user])
            db.commit()
            db.refresh(tenant)
            db.refresh(user)
            db.add(TenantMembership(tenant_id=tenant.id, user_id=user.id, role="tenant_admin", status="active"))
            db.commit()
            CrmPipelineService(db).ensure_default_pipeline(tenant.id)
            return tenant, user

    async def _auth_context_override(self):
        with SessionLocal() as db:
            tenant = db.get(Tenant, self.tenant.id)
            user = db.get(User, self.user.id)
            membership = db.scalar(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == tenant.id,
                    TenantMembership.user_id == user.id,
                )
            )
            return AuthContext(user=user, tenant=tenant, membership=membership)

    def _seed_lead(self, tenant_id: str, email: str | None = "lead@example.com") -> str:
        with SessionLocal() as db:
            stage = CrmPipelineService(db).get_stage_by_key(tenant_id, "new")
            contact = CrmContact(tenant_id=tenant_id, name="Lead Test", email=email, company="Empresa")
            db.add(contact)
            db.commit()
            db.refresh(contact)
            lead = CrmLead(tenant_id=tenant_id, contact_id=contact.id, current_stage_id=stage.id, status="open")
            db.add(lead)
            db.commit()
            db.refresh(lead)
            return lead.id

    def _configure_resend(self, tenant_id: str | None = None):
        with SessionLocal() as db:
            tenant_id = tenant_id or self.tenant.id
            EmailConfigService(db).upsert_resend_config(
                tenant_id=tenant_id,
                sender_name="ServiGlobal IA",
                sender_email="comercial@mail.serviglobal-ia.com",
                reply_to="ventas@serviglobal.co",
                default_domain="mail.serviglobal-ia.com",
                status="active",
            )
            IntegrationService(db).upsert_resend(
                tenant_id=tenant_id,
                display_name="Resend",
                config={"sender_email": "comercial@mail.serviglobal-ia.com"},
                api_key="re_secret_test",
            )

    def _payload(self, preview_only: bool = False):
        return {
            "template_key": "lead_proposal",
            "subject": "Propuesta comercial ServiGlobal IA",
            "message": "Hola, adjunto la propuesta conversada.",
            "asset_ids": [],
            "preview_only": preview_only,
        }

    def test_email_action_requires_contact_email(self):
        self._configure_resend()
        lead_id = self._seed_lead(self.tenant.id, email=None)

        response = self.client.post(f"/api/v1/crm/leads/{lead_id}/actions/email", json=self._payload())

        self.assertEqual(response.status_code, 422)

    def test_email_action_requires_active_resend_config(self):
        lead_id = self._seed_lead(self.tenant.id)

        response = self.client.post(f"/api/v1/crm/leads/{lead_id}/actions/email", json=self._payload())

        self.assertEqual(response.status_code, 422)

    def test_email_action_sends_with_resend_mock(self):
        self._configure_resend()
        lead_id = self._seed_lead(self.tenant.id)

        with patch("app.services.email_send_service.ResendService") as service_cls:
            service_cls.return_value.send_email.return_value = "email_provider_1"
            response = self.client.post(f"/api/v1/crm/leads/{lead_id}/actions/email", json=self._payload())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provider_email_id"], "email_provider_1")

    def test_email_action_creates_email_send_record(self):
        self._configure_resend()
        lead_id = self._seed_lead(self.tenant.id)
        with patch("app.services.email_send_service.ResendService") as service_cls:
            service_cls.return_value.send_email.return_value = "email_provider_1"
            self.client.post(f"/api/v1/crm/leads/{lead_id}/actions/email", json=self._payload())

        with SessionLocal() as db:
            send = db.scalar(select(TenantEmailSend).where(TenantEmailSend.lead_id == lead_id))
        self.assertIsNotNone(send)
        self.assertEqual(send.status, "sent")

    def test_email_action_creates_crm_activity_email_sent(self):
        self._configure_resend()
        lead_id = self._seed_lead(self.tenant.id)
        with patch("app.services.email_send_service.ResendService") as service_cls:
            service_cls.return_value.send_email.return_value = "email_provider_1"
            self.client.post(f"/api/v1/crm/leads/{lead_id}/actions/email", json=self._payload())

        with SessionLocal() as db:
            count = db.scalar(
                select(func.count()).select_from(CrmActivity).where(
                    CrmActivity.lead_id == lead_id,
                    CrmActivity.activity_type == "email_sent",
                )
            )
        self.assertEqual(count, 1)

    def test_email_action_records_failed_send(self):
        self._configure_resend()
        lead_id = self._seed_lead(self.tenant.id)
        with patch("app.services.email_send_service.ResendService") as service_cls:
            service_cls.return_value.send_email.side_effect = ResendServiceError("resend down")
            response = self.client.post(f"/api/v1/crm/leads/{lead_id}/actions/email", json=self._payload())

        self.assertEqual(response.status_code, 502)
        with SessionLocal() as db:
            send = db.scalar(select(TenantEmailSend).where(TenantEmailSend.lead_id == lead_id))
            activity_count = db.scalar(
                select(func.count()).select_from(CrmActivity).where(
                    CrmActivity.lead_id == lead_id,
                    CrmActivity.activity_type == "email_failed",
                )
            )
        self.assertEqual(send.status, "failed")
        self.assertEqual(activity_count, 1)

    def test_email_action_does_not_cross_tenant(self):
        self._configure_resend()
        other_lead_id = self._seed_lead(self.other_tenant.id)

        response = self.client.post(f"/api/v1/crm/leads/{other_lead_id}/actions/email", json=self._payload())

        self.assertEqual(response.status_code, 404)

    def test_email_action_preview_does_not_send(self):
        self._configure_resend()
        lead_id = self._seed_lead(self.tenant.id)
        with patch("app.services.email_send_service.ResendService") as service_cls:
            response = self.client.post(
                f"/api/v1/crm/leads/{lead_id}/actions/email",
                json=self._payload(preview_only=True),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "preview")
        service_cls.return_value.send_email.assert_not_called()
        with SessionLocal() as db:
            send_count = db.scalar(select(func.count()).select_from(TenantEmailSend))
        self.assertEqual(send_count, 0)


if __name__ == "__main__":
    unittest.main()
