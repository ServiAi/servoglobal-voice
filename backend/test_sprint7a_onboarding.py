"""Sprint 7A: Multitenant Onboarding — comprehensive tests."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
import unittest

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
TEST_DB_PATH = Path("serviai_sprint7a_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")

from fastapi.testclient import TestClient

from app.api.auth.deps import AuthContext, get_current_auth_context
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.analytics import Agent
from app.models.identity import Tenant, TenantMembership, User
from app.services.auth0_service import AuthenticatedIdentity
from app.services.identity_service import IdentityService


class Sprint7AOnboardingTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        TEST_DB_PATH.unlink(missing_ok=True)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        app.dependency_overrides.clear()
        self.client = TestClient(app)
        # Seed an internal admin user and override auth context
        self.admin_user = self._seed_internal_admin()
        self._override_auth_context()

    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def _seed_internal_admin(self) -> User:
        """Pre-create an internal platform admin user in the test DB."""
        user = User(
            email="admin@test.com",
            name="Test Admin",
            is_internal=True,
            external_auth_id=None,
        )
        with SessionLocal() as db:
            db.add(user)
            db.commit()
            db.refresh(user)
        return user

    def _override_auth_context(self):
        """Override get_current_auth_context to return our internal admin."""
        async def _auth_context_override():
            return AuthContext(
                user=self.admin_user,
                tenant=Tenant(name="System", slug="system", timezone="UTC"),
                membership=TenantMembership(
                    tenant_id=self.admin_user.id,
                    user_id=self.admin_user.id,
                    role="admin",
                    status="active",
                ),
            )
        app.dependency_overrides[get_current_auth_context] = _auth_context_override

    def _make_admin_payload(self, slug: str, agent_count: int = 0) -> dict:
        base = {
            "name": "Test Agency",
            "slug": slug,
            "timezone": "America/Bogota",
            "status": "active",
            "admin": {
                "name": "Admin User",
                "email": f"admin-{uuid.uuid4().hex[:6]}@agency.com",
                "role": "admin",
            },
            "agents": [],
        }
        if agent_count > 0:
            base["agents"] = [
                {
                    "name": f"Agent {i}",
                    "external_provider": "ultravox",
                    "external_agent_id": f"uv-{i:03d}",
                    "channel_type": "voice",
                    "status": "active",
                }
                for i in range(agent_count)
            ]
        return base

    # ============================================================
    # TEST: Migration — external_auth_id is nullable
    # ============================================================

    def test_migration_external_auth_id_nullable(self):
        """Verify external_auth_id column is nullable in the database."""
        user = User(
            email=f"noauth-{uuid.uuid4().hex[:8]}@test.com",
            name="No Auth User",
            external_auth_id=None,
            is_internal=False,
        )
        with SessionLocal() as db:
            db.add(user)
            db.commit()
            db.refresh(user)
            self.assertIsNotNone(user.id)
            self.assertIsNone(user.external_auth_id)

    # ============================================================
    # TEST: IdentityService — _resolve_user_by_email links sub
    # ============================================================

    def test_identity_service_links_sub_on_first_login(self):
        """Pre-provisioned user without external_auth_id gets linked on first login."""
        from app.services.identity_service import IdentityService

        user = User(
            email="preprovision@test.com",
            name="Preprovisioned User",
            external_auth_id=None,
            is_internal=False,
        )
        with SessionLocal() as db:
            db.add(user)
            db.commit()
            db.refresh(user)
            self.assertIsNone(user.external_auth_id)

            service = IdentityService(db)
            identity = AuthenticatedIdentity(
                external_auth_id="auth0|123456",
                email="preprovision@test.com",
                name="Preprovisioned User",
            )
            linked_user = service.resolve_user(identity)
            self.assertEqual(linked_user.id, user.id)
            self.assertEqual(linked_user.external_auth_id, "auth0|123456")

    def test_identity_service_does_not_create_duplicate_on_link(self):
        """When a user is linked, no duplicate is created."""
        from app.services.identity_service import IdentityService

        user = User(
            email="nopreprovision@test.com",
            name="No Preprovision",
            external_auth_id=None,
            is_internal=False,
        )
        with SessionLocal() as db:
            db.add(user)
            db.commit()
            db.refresh(user)

            service = IdentityService(db)
            identity = AuthenticatedIdentity(
                external_auth_id="auth0|789",
                email="nopreprovision@test.com",
                name="No Preprovision",
            )
            linked_user = service.resolve_user(identity)
            self.assertEqual(linked_user.id, user.id)

            count = db.query(User).filter(User.email == "nopreprovision@test.com").count()
            self.assertEqual(count, 1)

    def test_identity_service_creates_new_user_when_no_email_match(self):
        """When no user matches the email, a new user is created."""
        from app.services.identity_service import IdentityService

        with SessionLocal() as db:
            service = IdentityService(db)
            identity = AuthenticatedIdentity(
                external_auth_id="auth0|999",
                email="brandnew@test.com",
                name="Brand New",
            )
            new_user = service.resolve_user(identity)
            self.assertEqual(new_user.external_auth_id, "auth0|999")
            self.assertEqual(new_user.email, "brandnew@test.com")
            self.assertEqual(new_user.name, "Brand New")

            db_user = db.query(User).filter(User.email == "brandnew@test.com").first()
            self.assertIsNotNone(db_user)

    # ============================================================
    # TEST: OnboardingService — create_tenant (happy path)
    # ============================================================

    def test_create_tenant_happy_path(self):
        """Create a tenant with admin and agents successfully."""
        slug = f"test-tenant-{uuid.uuid4().hex[:8]}"
        response = self.client.post(
            "/api/v1/admin/tenants",
            json=self._make_admin_payload(slug, agent_count=1),
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIsNotNone(data["id"])
        self.assertEqual(data["name"], "Test Agency")
        self.assertEqual(data["slug"], slug)
        self.assertTrue(data["is_ready_for_calls"])
        self.assertEqual(len(data["agents"]), 1)
        self.assertEqual(data["agents"][0]["external_agent_id"], "uv-000")

        with SessionLocal() as db:
            tenant = db.query(Tenant).filter(Tenant.slug == slug).first()
            self.assertIsNotNone(tenant)
            self.assertEqual(tenant.status, "active")

    # ============================================================
    # TEST: OnboardingService — duplicate slug rejected
    # ============================================================

    def test_create_tenant_duplicate_slug_rejected(self):
        """Two tenants with the same slug should fail."""
        slug = f"dup-tenant-{uuid.uuid4().hex[:8]}"
        payload = self._make_admin_payload(slug, agent_count=0)

        resp1 = self.client.post("/api/v1/admin/tenants", json=payload)
        self.assertEqual(resp1.status_code, 201)

        payload["name"] = "Second Agency"
        payload["admin"]["email"] = f"admin2-{uuid.uuid4().hex[:6]}@agency.com"
        resp2 = self.client.post("/api/v1/admin/tenants", json=payload)
        self.assertEqual(resp2.status_code, 409)

    # ============================================================
    # TEST: OnboardingService — tenant creation is transactional
    # ============================================================

    def test_tenant_creation_is_transactional(self):
        """All parts of tenant creation succeed in a single transaction."""
        slug = f"tx-tenant-{uuid.uuid4().hex[:8]}"
        response = self.client.post(
            "/api/v1/admin/tenants",
            json=self._make_admin_payload(slug, agent_count=1),
        )
        self.assertEqual(response.status_code, 201)

        with SessionLocal() as db:
            tenant = db.query(Tenant).filter(Tenant.slug == slug).first()
            self.assertIsNotNone(tenant)

            membership = (
                db.query(TenantMembership)
                .filter(TenantMembership.tenant_id == tenant.id)
                .first()
            )
            self.assertIsNotNone(membership)
            self.assertEqual(membership.role, "admin")

            agent = db.query(Agent).filter(Agent.tenant_id == tenant.id).first()
            self.assertIsNotNone(agent)
            self.assertEqual(agent.external_agent_id, "uv-000")

    # ============================================================
    # TEST: Admin guard — non-internal user is rejected
    # ============================================================

    def test_admin_guard_rejects_non_internal_user(self):
        """A non-internal user should get 403 on admin endpoints."""
        non_internal = User(
            email=f"external-{uuid.uuid4().hex[:6]}@test.com",
            name="External User",
            is_internal=False,
            external_auth_id="auth0|ext123",
        )

        async def _auth_context_override():
            return AuthContext(
                user=non_internal,
                tenant=Tenant(name="System", slug="system", timezone="UTC"),
                membership=TenantMembership(
                    tenant_id=non_internal.id,
                    user_id=non_internal.id,
                    role="member",
                    status="active",
                ),
            )
        app.dependency_overrides[get_current_auth_context] = _auth_context_override

        response = self.client.get("/api/v1/admin/tenants")
        self.assertEqual(response.status_code, 403)

    # ============================================================
    # TEST: Admin guard — internal user is allowed
    # ============================================================

    def test_admin_guard_allows_internal_user(self):
        """An internal user should be able to access admin endpoints."""
        # Already seeded in setUp via _seed_internal_admin
        response = self.client.get("/api/v1/admin/tenants")
        self.assertEqual(response.status_code, 200)

    # ============================================================
    # TEST: OnboardingService — list_tenants returns all
    # ============================================================

    def test_list_tenants_returns_all(self):
        """list_tenants should return all tenants."""
        slug1 = f"list-tenant-{uuid.uuid4().hex[:8]}"
        slug2 = f"list-tenant-{uuid.uuid4().hex[:8]}"

        for i, slug in enumerate([slug1, slug2], 1):
            payload = self._make_admin_payload(slug, agent_count=0)
            payload["name"] = f"List Tenant {i}"
            payload["admin"]["email"] = f"admin{i}-list-{uuid.uuid4().hex[:6]}@test.com"
            resp = self.client.post("/api/v1/admin/tenants", json=payload)
            self.assertEqual(resp.status_code, 201)

        response = self.client.get("/api/v1/admin/tenants")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreaterEqual(len(data), 2)

    # ============================================================
    # TEST: OnboardingService — add_agent after creation
    # ============================================================

    def test_add_agent_after_creation(self):
        """Add an agent to an existing tenant."""
        slug = f"agent-test-{uuid.uuid4().hex[:8]}"
        create_resp = self.client.post(
            "/api/v1/admin/tenants",
            json=self._make_admin_payload(slug, agent_count=0),
        )
        self.assertEqual(create_resp.status_code, 201)
        tenant_id = create_resp.json()["id"]

        add_resp = self.client.post(
            f"/api/v1/admin/tenants/{tenant_id}/agents",
            json={
                "name": "Voice Agent",
                "external_provider": "ultravox",
                "external_agent_id": "uv-added-001",
                "channel_type": "voice",
                "status": "active",
            },
        )
        self.assertEqual(add_resp.status_code, 201)
        data = add_resp.json()
        self.assertEqual(data["external_agent_id"], "uv-added-001")
        self.assertEqual(data["tenant_id"], tenant_id)

    # ============================================================
    # TEST: OnboardingService — add_membership after creation
    # ============================================================

    def test_add_membership_after_creation(self):
        """Add a membership to an existing tenant."""
        slug = f"mem-test-{uuid.uuid4().hex[:8]}"
        member_email = f"member-{uuid.uuid4().hex[:6]}@agency.com"

        create_resp = self.client.post(
            "/api/v1/admin/tenants",
            json={
                "name": "Membership Test Agency",
                "slug": slug,
                "timezone": "America/Bogota",
                "status": "active",
                "admin": {
                    "name": "Admin",
                    "email": f"admin-{uuid.uuid4().hex[:6]}@mem.com",
                    "role": "admin",
                },
                "agents": [],
            },
        )
        self.assertEqual(create_resp.status_code, 201)
        tenant_id = create_resp.json()["id"]

        # First create the member user
        member_user = User(
            email=member_email,
            name="Test Member",
            is_internal=False,
            external_auth_id="auth0|member123",
        )
        with SessionLocal() as db:
            db.add(member_user)
            db.commit()

        add_resp = self.client.post(
            f"/api/v1/admin/tenants/{tenant_id}/memberships",
            json={
                "email": member_email,
                "role": "member",
            },
        )
        self.assertEqual(add_resp.status_code, 201)
        data = add_resp.json()
        self.assertEqual(data["role"], "member")
        self.assertEqual(data["tenant_id"], tenant_id)

    # ============================================================
    # TEST: Tenant response includes is_ready_for_calls
    # ============================================================

    def test_tenant_response_is_ready_for_calls(self):
        """is_ready_for_calls should be True when agents exist, False otherwise."""
        slug = f"ready-test-{uuid.uuid4().hex[:8]}"

        create_resp = self.client.post(
            "/api/v1/admin/tenants",
            json=self._make_admin_payload(slug, agent_count=0),
        )
        self.assertEqual(create_resp.status_code, 201)
        self.assertFalse(create_resp.json()["is_ready_for_calls"])

        tenant_id = create_resp.json()["id"]
        detail_resp = self.client.get(f"/api/v1/admin/tenants/{tenant_id}")
        self.assertEqual(detail_resp.status_code, 200)
        self.assertFalse(detail_resp.json()["is_ready_for_calls"])

        add_resp = self.client.post(
            f"/api/v1/admin/tenants/{tenant_id}/agents",
            json={
                "name": "Voice Agent",
                "external_provider": "ultravox",
                "external_agent_id": "uv-ready-001",
                "channel_type": "voice",
                "status": "active",
            },
        )
        self.assertEqual(add_resp.status_code, 201)

        detail_resp = self.client.get(f"/api/v1/admin/tenants/{tenant_id}")
        self.assertEqual(detail_resp.status_code, 200)
        self.assertTrue(detail_resp.json()["is_ready_for_calls"])

    # ============================================================
    # TEST: Tenant update
    # ============================================================

    def test_update_tenant(self):
        """Update a tenant's name and timezone."""
        slug = f"update-test-{uuid.uuid4().hex[:8]}"

        create_resp = self.client.post(
            "/api/v1/admin/tenants",
            json={
                "name": "Original Name",
                "slug": slug,
                "timezone": "America/New_York",
                "status": "active",
                "admin": {
                    "name": "Admin",
                    "email": f"admin-{uuid.uuid4().hex[:6]}@update.com",
                    "role": "admin",
                },
                "agents": [],
            },
        )
        self.assertEqual(create_resp.status_code, 201)
        tenant_id = create_resp.json()["id"]

        update_resp = self.client.patch(
            f"/api/v1/admin/tenants/{tenant_id}",
            json={
                "name": "Updated Name",
                "timezone": "Europe/Madrid",
                "status": "active",
            },
        )
        self.assertEqual(update_resp.status_code, 200)
        data = update_resp.json()
        self.assertEqual(data["name"], "Updated Name")
        self.assertEqual(data["timezone"], "Europe/Madrid")

        with SessionLocal() as db:
            tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
            self.assertIsNotNone(tenant)
            self.assertEqual(tenant.name, "Updated Name")
            self.assertEqual(tenant.timezone, "Europe/Madrid")


if __name__ == "__main__":
    unittest.main()
