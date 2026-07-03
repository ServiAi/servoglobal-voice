from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")
os.environ["SERVIAI_TEST_SECRET_FALLBACK"] = "1"
TEST_DB_PATH = Path("serviai_admin_tenant_integrations_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.auth.deps import AuthContext, get_current_auth_context
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.identity import Tenant, TenantMembership, User
from app.models.integrations import TenantBookingConfig, TenantIntegration
from app.services.resend_service import ResendService


class AdminTenantIntegrationTests(unittest.TestCase):
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
        self.is_internal = True # Defaults to platform admin
        app.dependency_overrides[get_current_auth_context] = self._auth_context_override

    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def _seed_tenant_user(self):
        with SessionLocal() as db:
            tenant = Tenant(name="Tenant A", slug="tenant-a")
            user = User(email="admin@example.com", name="Admin", status="active", is_internal=True)
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
            user.is_internal = self.is_internal
            membership = db.scalar(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == tenant.id,
                    TenantMembership.user_id == user.id,
                )
            )
            return AuthContext(user=user, tenant=tenant, membership=membership)

    def _configure(self, tenant_id: str, payload: dict | None = None):
        if payload is None:
            payload = {
                "sender_name": "ServiGlobal IA",
                "sender_email": "comercial@mail.serviglobal-ia.com",
                "reply_to": "ventas@serviglobal.co",
                "default_domain": "mail.serviglobal-ia.com",
                "resend_api_key": "re_secret_test",
            }
        return self.client.post(
            f"/api/v1/admin/tenants/{tenant_id}/integrations/resend/config",
            json=payload,
        )

    def test_platform_admin_can_fetch_tenant_integrations(self):
        self.is_internal = True
        response = self.client.get(f"/api/v1/admin/tenants/{self.tenant.id}/integrations")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["provider"], "resend")

    def test_platform_admin_can_configure_resend_for_specific_tenant(self):
        self.is_internal = True
        response = self._configure(self.tenant.id)
        self.assertEqual(response.status_code, 200)
        
        with SessionLocal() as db:
            integration = db.scalar(select(TenantIntegration).where(TenantIntegration.tenant_id == self.tenant.id))
        self.assertIsNotNone(integration)
        self.assertNotIn("re_secret_test", integration.secrets_json_encrypted)

    def test_platform_admin_config_does_not_expose_api_key(self):
        self.is_internal = True
        response = self._configure(self.tenant.id)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["has_secret"])
        self.assertNotIn("resend_api_key", payload)
        self.assertNotIn("re_secret_test", response.text)

    def test_platform_admin_can_send_resend_test_for_specific_tenant(self):
        self.is_internal = True
        self._configure(self.tenant.id)
        
        with patch("app.services.email_send_service.ResendService") as service_cls:
            service_cls.return_value.send_test_email.return_value = "email_test_admin"
            response = self.client.post(
                f"/api/v1/admin/tenants/{self.tenant.id}/integrations/resend/test",
                json={"to_email": "dest@example.com"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provider_email_id"], "email_test_admin")

    def test_platform_admin_calcom_test_without_config_returns_422(self):
        self.is_internal = True
        response = self.client.post(f"/api/v1/admin/tenants/{self.tenant.id}/integrations/calcom/test")

        self.assertEqual(response.status_code, 422)
        self.assertIn("Cal.com booking config is not active", response.json()["detail"])

    def test_platform_admin_calcom_test_failure_returns_controlled_response(self):
        self.is_internal = True
        self.client.post(
            f"/api/v1/admin/tenants/{self.tenant.id}/integrations/calcom/config",
            json={
                "status": "active",
                "calendar_mode": "cal_managed",
                "cal_api_key": "cal_secret_test",
                "default_event_type_id": 123,
                "default_timezone": "America/Bogota",
                "default_language": "es",
                "default_length_minutes": 30,
            },
        )

        with patch(
            "app.services.booking_config_service.CalComClient.get_available_slots",
            side_effect=Exception("Cal.com API error 401: invalid token cal_secret_test"),
        ):
            response = self.client.post(f"/api/v1/admin/tenants/{self.tenant.id}/integrations/calcom/test")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertIn("Cal.com API error 401", payload["error_message"])
        self.assertNotIn("cal_secret_test", response.text)
        with SessionLocal() as db:
            config = db.scalar(select(TenantBookingConfig).where(TenantBookingConfig.tenant_id == self.tenant.id))
        self.assertEqual(config.status, "active")

        with patch("app.services.booking_config_service.CalComClient.get_available_slots", return_value={"available_slots": []}):
            retry = self.client.post(f"/api/v1/admin/tenants/{self.tenant.id}/integrations/calcom/test")

        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json()["status"], "active")

        with SessionLocal() as db:
            config = db.scalar(select(TenantBookingConfig).where(TenantBookingConfig.tenant_id == self.tenant.id))
            config.status = "error"
            db.commit()

        with patch("app.services.booking_config_service.CalComClient.get_available_slots", return_value={"available_slots": []}):
            retry_from_error = self.client.post(f"/api/v1/admin/tenants/{self.tenant.id}/integrations/calcom/test")

        self.assertEqual(retry_from_error.status_code, 200)
        self.assertEqual(retry_from_error.json()["status"], "active")

    def test_tenant_admin_cannot_use_admin_tenant_integration_endpoint(self):
        self.is_internal = False
        response = self.client.get(f"/api/v1/admin/tenants/{self.tenant.id}/integrations")
        self.assertEqual(response.status_code, 403)
        self.assertIn("Internal platform access required", response.json()["detail"])

        response = self.client.post(
            f"/api/v1/admin/tenants/{self.tenant.id}/integrations/resend/config",
            json={
                "sender_name": "ServiGlobal IA",
                "sender_email": "comercial@mail.serviglobal-ia.com",
                "resend_api_key": "re_secret_test",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_endpoint_returns_404_for_unknown_tenant(self):
        self.is_internal = True
        unknown_id = "nonexistent-tenant-id"
        
        response = self.client.get(f"/api/v1/admin/tenants/{unknown_id}/integrations")
        self.assertEqual(response.status_code, 404)
        
        response = self.client.post(
            f"/api/v1/admin/tenants/{unknown_id}/integrations/resend/config",
            json={
                "sender_name": "ServiGlobal IA",
                "sender_email": "comercial@mail.serviglobal-ia.com",
                "resend_api_key": "re_secret_test",
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_admin_config_preserves_existing_secret_when_api_key_missing(self):
        self.is_internal = True
        
        # Configure first time with API key
        res1 = self._configure(self.tenant.id, {
            "sender_name": "ServiGlobal IA",
            "sender_email": "comercial@mail.serviglobal-ia.com",
            "resend_api_key": "first_key",
        })
        self.assertEqual(res1.status_code, 200)
        self.assertTrue(res1.json()["has_secret"])
        
        # Update config WITHOUT sending the API key again
        res2 = self._configure(self.tenant.id, {
            "sender_name": "ServiGlobal IA Updated",
            "sender_email": "comercial@mail.serviglobal-ia.com",
            "resend_api_key": None,
        })
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(res2.json()["has_secret"])
        self.assertEqual(res2.json()["sender_name"], "ServiGlobal IA Updated")
