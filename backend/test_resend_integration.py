from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")
os.environ["SERVIAI_TEST_SECRET_FALLBACK"] = "1"
TEST_DB_PATH = Path("serviai_resend_integration_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.auth.deps import AuthContext, get_current_auth_context
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.identity import Tenant, TenantMembership, User
from app.models.integrations import TenantIntegration
from app.services.resend_service import ResendService, ResendServiceError, _sanitize_resend_error


class _Response:
    status_code = 200
    text = '{"id":"email_test"}'

    def json(self):
        return {"id": "email_test"}


class _Client:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def post(self, *args, **kwargs):
        return _Response()


class ResendIntegrationTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        TEST_DB_PATH.unlink(missing_ok=True)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        app.dependency_overrides.clear()
        self.client = TestClient(app)
        self.tenant, self.user = self._seed_tenant_user()
        app.dependency_overrides[get_current_auth_context] = self._auth_context_override

    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def _seed_tenant_user(self):
        with SessionLocal() as db:
            tenant = Tenant(name="Tenant A", slug="tenant-a")
            user = User(email="admin@example.com", name="Admin", status="active")
            db.add_all([tenant, user])
            db.commit()
            db.refresh(tenant)
            db.refresh(user)
            db.add(TenantMembership(tenant_id=tenant.id, user_id=user.id, role="tenant_admin", status="active"))
            db.commit()
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

    def _configure(self):
        return self.client.post(
            "/api/v1/integrations/resend/config",
            json={
                "sender_name": "ServiGlobal IA",
                "sender_email": "comercial@mail.serviglobal-ia.com",
                "reply_to": "ventas@serviglobal.co",
                "default_domain": "mail.serviglobal-ia.com",
                "resend_api_key": "re_secret_test",
            },
        )

    def test_resend_config_can_be_saved_per_tenant(self):
        response = self._configure()

        self.assertEqual(response.status_code, 200)
        with SessionLocal() as db:
            integration = db.scalar(select(TenantIntegration).where(TenantIntegration.tenant_id == self.tenant.id))
        self.assertIsNotNone(integration)
        self.assertNotIn("re_secret_test", integration.secrets_json_encrypted)

    def test_resend_config_does_not_expose_api_key(self):
        response = self._configure()
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["has_secret"])
        self.assertNotIn("resend_api_key", payload)
        self.assertNotIn("re_secret_test", response.text)

    def test_resend_test_email_requires_config(self):
        response = self.client.post("/api/v1/integrations/resend/test", json={"to_email": "dest@example.com"})

        self.assertEqual(response.status_code, 422)

    def test_resend_test_email_sends_with_mock(self):
        self._configure()
        with patch("app.services.email_send_service.ResendService") as service_cls:
            service_cls.return_value.send_test_email.return_value = "email_test_1"
            response = self.client.post("/api/v1/integrations/resend/test", json={"to_email": "dest@example.com"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provider_email_id"], "email_test_1")

    def test_resend_test_failure_does_not_disable_retry(self):
        self._configure()
        with patch("app.services.email_send_service.ResendService") as service_cls:
            service_cls.return_value.send_test_email.side_effect = ResendServiceError("resend down")
            response = self.client.post("/api/v1/integrations/resend/test", json={"to_email": "dest@example.com"})

        self.assertEqual(response.status_code, 502)

        with patch("app.services.email_send_service.ResendService") as service_cls:
            service_cls.return_value.send_test_email.return_value = "email_test_2"
            response = self.client.post("/api/v1/integrations/resend/test", json={"to_email": "dest@example.com"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provider_email_id"], "email_test_2")

    def test_logs_do_not_include_resend_api_key_or_full_email_or_payload(self):
        service = ResendService()
        with patch("app.services.resend_service.httpx.Client", _Client):
            with self.assertLogs("app.services.resend_service", level="INFO") as logs:
                service.send_email(
                    api_key="re_secret_test",
                    from_email="sender@example.com",
                    to_email="person@example.com",
                    subject="Hello",
                    html="<p>full html payload</p>",
                    text="full text payload",
                    tenant_id="tenant-1",
                    lead_id="lead-1",
                    template_key="lead_proposal",
                )
        output = "\n".join(logs.output)
        self.assertNotIn("re_secret_test", output)
        self.assertNotIn("person@example.com", output)
        self.assertNotIn("full html payload", output)
        self.assertNotIn("full text payload", output)

    def test_resend_error_sanitizer_redacts_email_phone_and_api_key(self):
        raw_error = (
            "Resend error for person@example.com phone +57 300 123 4567\n"
            "api_key=re_secret_test Authorization: token.secret.value Bearer bearer.secret.value"
        )

        sanitized = _sanitize_resend_error(raw_error)

        self.assertNotIn("person@example.com", sanitized)
        self.assertNotIn("+57 300 123 4567", sanitized)
        self.assertNotIn("re_secret_test", sanitized)
        self.assertNotIn("token.secret.value", sanitized)
        self.assertNotIn("bearer.secret.value", sanitized)
        self.assertNotIn("\n", sanitized)
        self.assertIn("[redacted-email]", sanitized)
        self.assertIn("[redacted-phone]", sanitized)
        self.assertIn("[redacted-api-key]", sanitized)
        self.assertIn("Authorization [redacted-token]", sanitized)
        self.assertIn("Bearer [redacted-token]", sanitized)
        self.assertLessEqual(len(sanitized), 300)


if __name__ == "__main__":
    unittest.main()
