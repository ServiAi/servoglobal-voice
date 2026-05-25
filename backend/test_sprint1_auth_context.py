import os
from pathlib import Path
import unittest

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
TEST_DB_PATH = Path("serviai_sprint1_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")

from fastapi.testclient import TestClient

from app.api.auth.deps import get_current_identity
from app.core.config import settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.identity import AccessAuditLog, Tenant, TenantMembership, User
from app.services.auth0_service import AuthenticatedIdentity
from app.services.bootstrap_service import IdentityBootstrapService


class Sprint1AuthContextTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        TEST_DB_PATH.unlink(missing_ok=True)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        app.dependency_overrides.clear()
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def override_identity(self, external_auth_id: str, email: str | None = "user@example.com"):
        async def _identity_override():
            return AuthenticatedIdentity(
                external_auth_id=external_auth_id,
                email=email,
                name="Test User",
                claims={"sub": external_auth_id, "email": email} if email else {"sub": external_auth_id},
            )

        app.dependency_overrides[get_current_identity] = _identity_override

    def seed_user_with_membership(self, role: str = "tenant_admin") -> tuple[User, Tenant]:
        with SessionLocal() as db:
            tenant = Tenant(name="Empresa Demo", slug="empresa-demo")
            user = User(
                external_auth_id="auth0|active-user",
                email="active@example.com",
                name="Active User",
                is_internal=False,
                status="active",
            )
            db.add_all([tenant, user])
            db.commit()
            db.refresh(tenant)
            db.refresh(user)
            db.add(
                TenantMembership(
                    tenant_id=tenant.id,
                    user_id=user.id,
                    role=role,
                    status="active",
                )
            )
            db.commit()
            return user, tenant

    def test_me_returns_internal_context_for_active_membership(self):
        user, tenant = self.seed_user_with_membership(role="tenant_analyst")
        self.override_identity("auth0|active-user", "active@example.com")

        response = self.client.get("/api/v1/me", headers={"Authorization": "Bearer test"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["user_id"], user.id)
        self.assertEqual(payload["email"], "active@example.com")
        self.assertEqual(payload["name"], "Test User")
        self.assertEqual(payload["tenant_id"], tenant.id)
        self.assertEqual(payload["tenant_name"], "Empresa Demo")
        self.assertEqual(payload["role"], "tenant_analyst")
        self.assertFalse(payload["is_internal"])

    def test_me_blocks_authenticated_user_without_membership(self):
        self.override_identity("auth0|no-membership", "new@example.com")

        response = self.client.get("/api/v1/me", headers={"Authorization": "Bearer test"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"],
            "Authenticated user has no active tenant membership",
        )

    def test_me_resolves_tenant_and_role_from_internal_membership(self):
        _, tenant = self.seed_user_with_membership(role="tenant_viewer")
        self.override_identity("auth0|active-user", "active@example.com")

        response = self.client.get("/api/v1/me", headers={"Authorization": "Bearer test"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["tenant_id"], tenant.id)
        self.assertEqual(payload["role"], "tenant_viewer")

    def test_me_resolves_existing_user_when_access_token_has_no_email(self):
        user, _ = self.seed_user_with_membership()
        self.override_identity("auth0|active-user", None)

        response = self.client.get("/api/v1/me", headers={"Authorization": "Bearer test"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["user_id"], user.id)
        self.assertEqual(payload["email"], "active@example.com")

    def test_new_user_without_email_uses_stable_fallback_email(self):
        self.override_identity("auth0|no-email-user", None)

        response = self.client.get("/api/v1/me", headers={"Authorization": "Bearer test"})

        self.assertEqual(response.status_code, 403)
        with SessionLocal() as db:
            user = db.query(User).filter(User.external_auth_id == "auth0|no-email-user").one_or_none()
            self.assertIsNotNone(user)
            self.assertTrue(user.email.endswith("@auth0.local"))

    def test_me_writes_access_audit_log_on_success(self):
        user, tenant = self.seed_user_with_membership()
        self.override_identity("auth0|active-user", "active@example.com")

        response = self.client.get("/api/v1/me", headers={"Authorization": "Bearer test"})

        self.assertEqual(response.status_code, 200)
        with SessionLocal() as db:
            logs = db.query(AccessAuditLog).all()
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0].user_id, user.id)
            self.assertEqual(logs[0].tenant_id, tenant.id)
            self.assertEqual(logs[0].action, "profile_view")

    def test_public_routes_are_not_protected_by_auth0(self):
        health = self.client.get("/health")
        missing_turnstile = self.client.post("/api/v1/calls", json={})

        self.assertEqual(health.status_code, 200)
        self.assertEqual(missing_turnstile.status_code, 400)
        self.assertEqual(missing_turnstile.json()["detail"], "Turnstile token missing")

    def test_identity_bootstrap_is_idempotent(self):
        settings.BOOTSTRAP_TENANT_NAME = "Tenant Inicial"
        settings.BOOTSTRAP_TENANT_SLUG = "tenant-inicial"
        settings.BOOTSTRAP_TENANT_TIMEZONE = "America/Bogota"
        settings.BOOTSTRAP_USER_AUTH0_SUB = "auth0|bootstrap-user"
        settings.BOOTSTRAP_USER_EMAIL = "admin@example.com"
        settings.BOOTSTRAP_USER_NAME = "Admin Inicial"
        settings.BOOTSTRAP_USER_ROLE = "tenant_admin"

        with SessionLocal() as db:
            first = IdentityBootstrapService(db).run_initial_bootstrap()
            second = IdentityBootstrapService(db).run_initial_bootstrap()

            self.assertTrue(first.created_tenant)
            self.assertTrue(first.created_user)
            self.assertTrue(first.created_membership)
            self.assertFalse(second.created_tenant)
            self.assertFalse(second.created_user)
            self.assertFalse(second.created_membership)
            self.assertEqual(db.query(Tenant).count(), 1)
            self.assertEqual(db.query(User).count(), 1)
            self.assertEqual(db.query(TenantMembership).count(), 1)

    def test_identity_bootstrap_promotes_existing_auth0_user_to_internal(self):
        settings.BOOTSTRAP_TENANT_NAME = "Tenant Inicial"
        settings.BOOTSTRAP_TENANT_SLUG = "tenant-inicial"
        settings.BOOTSTRAP_TENANT_TIMEZONE = "America/Bogota"
        settings.BOOTSTRAP_USER_AUTH0_SUB = "auth0|bootstrap-user"
        settings.BOOTSTRAP_USER_EMAIL = "admin@example.com"
        settings.BOOTSTRAP_USER_NAME = "Admin Inicial"
        settings.BOOTSTRAP_USER_ROLE = "tenant_admin"

        with SessionLocal() as db:
            user = User(
                external_auth_id="auth0|bootstrap-user",
                email="admin@example.com",
                name="Auto-created User",
                is_internal=False,
                status="active",
            )
            db.add(user)
            db.commit()

            result = IdentityBootstrapService(db).run_initial_bootstrap()

            self.assertFalse(result.created_user)
            self.assertTrue(result.created_membership)
            db.refresh(user)
            self.assertTrue(user.is_internal)
            self.assertEqual(db.query(TenantMembership).count(), 1)


if __name__ == "__main__":
    unittest.main()
