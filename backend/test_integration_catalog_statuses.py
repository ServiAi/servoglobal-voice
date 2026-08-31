from __future__ import annotations

import os
from pathlib import Path
import unittest

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")
os.environ["SERVIAI_TEST_SECRET_FALLBACK"] = "1"
TEST_DB_PATH = Path("serviai_integration_catalog_statuses_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.auth.deps import AuthContext, get_current_auth_context
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.identity import Tenant, TenantMembership, User
from app.models.integrations import (
    TenantGoogleCalendarConnection,
    TenantIntegration,
    TenantVoiceProviderConfig,
    TenantWhatsAppConfig,
)


class IntegrationCatalogStatusesTests(unittest.TestCase):
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
            membership = db.scalar(select(TenantMembership).where(TenantMembership.tenant_id == tenant.id, TenantMembership.user_id == user.id))
            return AuthContext(user=user, tenant=tenant, membership=membership)

    def test_unconfigured_enabled_integrations_return_compact_statuses(self):
        response = self.client.get("/api/v1/integrations/statuses")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 5)
        self.assertTrue(all(item["status"] == "not_configured" for item in response.json()))
        self.assertTrue(all(set(item) == {"provider", "status"} for item in response.json()))

    def test_statuses_map_provider_state_and_omit_disabled_integrations(self):
        with SessionLocal() as db:
            db.add_all([
                TenantIntegration(tenant_id=self.tenant.id, provider="resend", enabled=True, status="active", secrets_json_encrypted="encrypted"),
                TenantIntegration(tenant_id=self.tenant.id, provider="calcom", enabled=False, status="inactive"),
                TenantWhatsAppConfig(tenant_id=self.tenant.id, status="active", phone_number_id="phone-id", last_error_message="sanitized failure"),
                TenantVoiceProviderConfig(tenant_id=self.tenant.id, status="inactive", display_name="Voice"),
                TenantGoogleCalendarConnection(tenant_id=self.tenant.id, user_id=self.user.id, status="connected", access_token_encrypted="encrypted"),
            ])
            db.commit()

        response = self.client.get("/api/v1/integrations/statuses")
        statuses = {item["provider"]: item["status"] for item in response.json()}

        self.assertEqual(response.status_code, 200)
        self.assertEqual(statuses, {"resend": "active", "voice": "configured", "whatsapp": "error", "google_calendar": "active"})
        self.assertNotIn("sanitized failure", response.text)
        self.assertNotIn("encrypted", response.text)


if __name__ == "__main__":
    unittest.main()
