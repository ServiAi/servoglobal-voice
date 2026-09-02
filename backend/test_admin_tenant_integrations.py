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
from app.models.crm import CrmWhatsAppMessage
from app.models.integrations import TenantBookingConfig, TenantIntegration, TenantWhatsAppConfig, TenantWhatsAppTemplate
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

    def test_platform_admin_can_disable_integration_and_tenant_cannot_access_it(self):
        response = self.client.patch(
            f"/api/v1/admin/tenants/{self.tenant.id}/integrations/availability/whatsapp",
            json={"enabled": False},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"provider": "whatsapp", "enabled": False})
        tenant_response = self.client.get("/api/v1/integrations/whatsapp/config")
        self.assertEqual(tenant_response.status_code, 404)

        availability = self.client.get("/api/v1/integrations/availability")
        self.assertEqual(availability.status_code, 200)
        whatsapp = next(item for item in availability.json() if item["provider"] == "whatsapp")
        self.assertFalse(whatsapp["enabled"])

    def test_platform_admin_can_fetch_compact_statuses_for_configurable_integrations(self):
        self.assertEqual(self._configure(self.tenant.id).status_code, 200)
        self.client.patch(
            f"/api/v1/admin/tenants/{self.tenant.id}/integrations/availability/resend",
            json={"enabled": False},
        )

        response = self.client.get(
            f"/api/v1/admin/tenants/{self.tenant.id}/integrations/statuses"
        )

        self.assertEqual(response.status_code, 200)
        statuses = {item["provider"]: item["status"] for item in response.json()}
        self.assertEqual(
            set(statuses),
            {"resend", "whatsapp", "voice", "calcom", "google_calendar"},
        )
        self.assertEqual(statuses["resend"], "active")
        self.assertTrue(all(set(item) == {"provider", "status"} for item in response.json()))
        self.assertNotIn("comercial@mail.serviglobal-ia.com", response.text)
        self.assertNotIn("re_secret_test", response.text)

    def test_integrations_default_to_enabled_and_can_be_reenabled_without_losing_config(self):
        initial = self.client.get(f"/api/v1/admin/tenants/{self.tenant.id}/integrations/availability")
        self.assertEqual(initial.status_code, 200)
        self.assertTrue(all(item["enabled"] for item in initial.json()))

        self.client.patch(
            f"/api/v1/admin/tenants/{self.tenant.id}/integrations/availability/resend",
            json={"enabled": False},
        )
        self.assertEqual(self._configure(self.tenant.id).status_code, 200)
        reenabled = self.client.patch(
            f"/api/v1/admin/tenants/{self.tenant.id}/integrations/availability/resend",
            json={"enabled": True},
        )
        self.assertEqual(reenabled.status_code, 200)
        tenant_integrations = self.client.get("/api/v1/integrations")
        self.assertEqual(tenant_integrations.status_code, 200)
        self.assertEqual(tenant_integrations.json()[0]["sender_email"], "comercial@mail.serviglobal-ia.com")

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

    def _configure_whatsapp(self):
        return self.client.post(
            f"/api/v1/admin/tenants/{self.tenant.id}/integrations/whatsapp/config",
            json={
                "phone_number_id": "phone-number-1",
                "business_account_id": "waba-1",
                "display_phone_number": "+573001112233",
                "default_language": "es",
                "status": "active",
                "access_token": "EA_secret_token_12345678901234567890",
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

        response = self.client.get(
            f"/api/v1/admin/tenants/{self.tenant.id}/integrations/statuses"
        )
        self.assertEqual(response.status_code, 403)

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

        response = self.client.get(
            f"/api/v1/admin/tenants/{unknown_id}/integrations/statuses"
        )
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

    def test_admin_sync_whatsapp_templates(self):
        self.assertEqual(self._configure_whatsapp().status_code, 200)
        provider_payload = {"data": [{
            "name": "appointment_reminder",
            "status": "APPROVED",
            "language": "es",
            "category": "UTILITY",
            "components": [{"type": "BODY", "text": "Hola {{1}}"}],
        }]}
        with patch("app.services.whatsapp_client.WhatsAppCloudClient.get_message_templates", return_value=provider_payload):
            response = self.client.post(
                f"/api/v1/admin/tenants/{self.tenant.id}/integrations/whatsapp/templates/sync"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["synced_count"], 1)

    def test_admin_send_whatsapp_test_message(self):
        self.assertEqual(self._configure_whatsapp().status_code, 200)
        with SessionLocal() as db:
            db.add(TenantWhatsAppTemplate(
                tenant_id=self.tenant.id,
                template_key="appointment_reminder",
                provider_template_name="appointment_reminder",
                name="appointment_reminder",
                category="utility",
                language="es",
                body="Hola",
                variables_json={"parameters": [], "meta_status": "APPROVED", "source": "meta_sync"},
                status="approved",
            ))
            db.commit()
        with patch(
            "app.services.whatsapp_client.WhatsAppCloudClient.send_template_message",
            return_value={"messages": [{"id": "wamid.admin-test"}]},
        ):
            response = self.client.post(
                f"/api/v1/admin/tenants/{self.tenant.id}/integrations/whatsapp/test-message",
                json={"to_phone": "+573001112233", "template_key": "appointment_reminder"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["to_phone_masked"], "***2233")
        with SessionLocal() as db:
            message = db.scalar(select(CrmWhatsAppMessage).where(CrmWhatsAppMessage.provider_message_id == "wamid.admin-test"))
        self.assertIsNone(message.lead_id)
