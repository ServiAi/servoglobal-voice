from __future__ import annotations

import os
from pathlib import Path
import unittest

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")
os.environ["SERVIAI_TEST_SECRET_FALLBACK"] = "1"
TEST_DB_PATH = Path("serviai_admin_membership_deletion_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.auth.deps import AuthContext, get_current_auth_context
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.identity import Tenant, TenantMembership, User
from app.services.google_calendar_oauth_service import GoogleCalendarOAuthService
from app.services.onboarding_service import OnboardingService


class AdminTenantMembershipDeletionTests(unittest.TestCase):
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
            self.tenant = Tenant(name="Test Tenant", slug="test-tenant", timezone="America/Bogota")
            db.add(self.tenant)
            db.flush()

            self.admin_user = User(
                email="admin@test.com",
                name="Admin User",
                is_internal=True,
                status="active",
            )
            db.add(self.admin_user)
            db.flush()

            self.admin_membership = TenantMembership(
                tenant_id=self.tenant.id,
                user_id=self.admin_user.id,
                role="tenant_admin",
                status="active",
            )
            db.add(self.admin_membership)

            self.analyst_user = User(
                email="analyst@test.com",
                name="Analyst User",
                is_internal=False,
                status="active",
            )
            db.add(self.analyst_user)
            db.flush()

            self.analyst_membership = TenantMembership(
                tenant_id=self.tenant.id,
                user_id=self.analyst_user.id,
                role="tenant_analyst",
                status="active",
            )
            db.add(self.analyst_membership)
            db.commit()

            self.tenant_id = self.tenant.id
            self.admin_membership_id = self.admin_membership.id
            self.analyst_membership_id = self.analyst_membership.id

        def override_auth_context():
            with SessionLocal() as db:
                user = db.scalar(select(User).where(User.id == self.admin_user.id))
                tenant = db.scalar(select(Tenant).where(Tenant.id == self.tenant_id))
                membership = db.scalar(select(TenantMembership).where(TenantMembership.id == self.admin_membership_id))
                return AuthContext(user=user, tenant=tenant, membership=membership)

        app.dependency_overrides[get_current_auth_context] = override_auth_context

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_cannot_delete_last_admin_membership(self):
        with SessionLocal() as db:
            service = OnboardingService(db)
            with self.assertRaisesRegex(ValueError, "No se puede eliminar la única membresía de administrador"):
                service.delete_membership(self.tenant_id, self.admin_membership_id)

    def test_delete_analyst_membership_service(self):
        with SessionLocal() as db:
            service = OnboardingService(db)
            res = service.delete_membership(self.tenant_id, self.analyst_membership_id)
            self.assertTrue(res["deleted"])

            remaining = service.list_memberships(self.tenant_id)
            self.assertEqual(len(remaining), 1)
            self.assertEqual(remaining[0].id, self.admin_membership_id)

    def test_delete_admin_membership_when_second_admin_exists(self):
        with SessionLocal() as db:
            user2 = User(email="admin2@test.com", name="Admin Two", is_internal=False, status="active")
            db.add(user2)
            db.flush()
            m2 = TenantMembership(tenant_id=self.tenant_id, user_id=user2.id, role="tenant_admin", status="active")
            db.add(m2)
            db.commit()
            m2_id = m2.id

            service = OnboardingService(db)
            res = service.delete_membership(self.tenant_id, m2_id)
            self.assertTrue(res["deleted"])

    def test_delete_membership_api_endpoint(self):
        response = self.client.delete(
            f"/api/v1/admin/tenants/{self.tenant_id}/memberships/{self.analyst_membership_id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["deleted"])

        # Check DB
        with SessionLocal() as db:
            m = db.scalar(select(TenantMembership).where(TenantMembership.id == self.analyst_membership_id))
            self.assertIsNone(m)

    def test_delete_membership_api_rejects_last_admin(self):
        response = self.client.delete(
            f"/api/v1/admin/tenants/{self.tenant_id}/memberships/{self.admin_membership_id}"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("No se puede eliminar", response.json()["detail"])

    def test_delete_membership_api_404(self):
        response = self.client.delete(
            f"/api/v1/admin/tenants/{self.tenant_id}/memberships/non-existent-id"
        )
        self.assertEqual(response.status_code, 404)

    def test_delete_admin_google_calendar_connection_api(self):
        with SessionLocal() as db:
            service = GoogleCalendarOAuthService(db)
            conn = service.store_connection(
                tenant_id=self.tenant_id,
                user_id=self.admin_user.id,
                google_account_email="admin_gc@test.com",
                access_token="tok",
                refresh_token="ref",
            )
            conn_id = conn.id

        response = self.client.delete(
            f"/api/v1/admin/tenants/{self.tenant_id}/integrations/google-calendar/connections/{conn_id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["deleted"])

        with SessionLocal() as db:
            service = GoogleCalendarOAuthService(db)
            self.assertEqual(len(service.list_connections(self.tenant_id)), 0)
