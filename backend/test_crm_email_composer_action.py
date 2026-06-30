from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")
os.environ["SERVIAI_TEST_SECRET_FALLBACK"] = "1"
TEST_DB_PATH = Path("serviai_email_composer_action_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"
os.environ["EMAIL_ASSETS_STORAGE_PATH"] = "storage/test-email-composer-assets"

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.auth.deps import AuthContext, get_current_auth_context
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.crm import CrmActivity, CrmContact, CrmLead
from app.models.identity import Tenant, TenantMembership, User
from app.models.integrations import TenantEmailAsset, TenantEmailSendAsset
from app.services.crm_pipeline_service import CrmPipelineService
from app.services.email_config_service import EmailConfigService
from app.services.form_service import FormService
from app.services.integration_service import IntegrationService
from app.services.storage_service import StorageService


class CrmEmailComposerActionTests(unittest.TestCase):
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
            contact = CrmContact(tenant_id=self.tenant_id, name="Ana", email="ana@example.com")
            db.add(contact)
            db.commit()
            db.refresh(contact)
            lead = CrmLead(tenant_id=self.tenant_id, contact_id=contact.id, current_stage_id=stage.id)
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

    def _asset(self):
        with SessionLocal() as db:
            storage_key = f"{self.tenant_id}/proposal.pdf"
            StorageService().upload_bytes(storage_key, b"pdf")
            asset = TenantEmailAsset(
                tenant_id=self.tenant_id,
                uploaded_by_user_id=self.user_id,
                original_filename="proposal.pdf",
                storage_key=storage_key,
                mime_type="application/pdf",
                file_size_bytes=3,
                checksum_sha256="0" * 64,
                visibility="private",
                status="uploaded",
            )
            db.add(asset)
            db.commit()
            db.refresh(asset)
            return asset.id

    def _form_token(self):
        with SessionLocal() as db:
            service = FormService(db)
            form = service.ensure_default_form(self.tenant_id)
            token_row, link = service.create_token(self.tenant_id, form.id, self.lead_id, 7)
            return token_row.id, link

    def test_preview_does_not_send_email(self):
        with patch("app.services.email_send_service.ResendService") as service_cls:
            response = self.client.post(
                f"/api/v1/crm/leads/{self.lead_id}/actions/email",
                json={
                    "subject": "Propuesta",
                    "content": "Hola {{contact_name}}",
                    "preview_only": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        service_cls.return_value.send_email.assert_not_called()
        self.assertEqual(response.json()["status"], "preview")

    def test_email_send_persists_send_assets(self):
        asset_id = self._asset()
        with patch("app.services.email_send_service.ResendService") as service_cls:
            service_cls.return_value.send_email.return_value = "email_1"
            response = self.client.post(
                f"/api/v1/crm/leads/{self.lead_id}/actions/email",
                json={"content": "Hola {{contact_name}}", "asset_ids": [asset_id]},
            )

        self.assertEqual(response.status_code, 200)
        with SessionLocal() as db:
            count = db.scalar(select(func.count()).select_from(TenantEmailSendAsset))
        self.assertEqual(count, 1)

    def test_email_with_form_link_records_form_link_sent(self):
        token_id, link = self._form_token()
        with patch("app.services.email_send_service.ResendService") as service_cls:
            service_cls.return_value.send_email.return_value = "email_1"
            response = self.client.post(
                f"/api/v1/crm/leads/{self.lead_id}/actions/email",
                json={
                    "content": f'<Button href="{link}">Completar formulario</Button>',
                    "form_token_ids": [token_id],
                },
            )

        self.assertEqual(response.status_code, 200)
        with SessionLocal() as db:
            count = db.scalar(select(func.count()).select_from(CrmActivity).where(CrmActivity.activity_type == "form_link_sent"))
        self.assertEqual(count, 1)

    def test_tenant_admin_cannot_access_admin_form_endpoints(self):
        response = self.client.get(f"/api/v1/admin/tenants/{self.tenant_id}/forms")

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
