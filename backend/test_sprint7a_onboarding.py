"""Sprint 7A: Multitenant Onboarding + Identity Risk Fix — comprehensive tests."""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
import unittest

import sqlalchemy as sa

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
TEST_DB_PATH = Path("serviai_sprint7a_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.auth.deps import AuthContext, get_current_auth_context
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.analytics import Agent
from app.models.identity import Tenant, TenantMembership, User
from app.services.auth0_service import AuthenticatedIdentity
from app.services.identity_service import IdentityService


class Sprint7AIdentityTests(unittest.TestCase):
    """Tests for identity risk fix: email uniqueness, link-by-first-login, ambiguity."""

    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        TEST_DB_PATH.unlink(missing_ok=True)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        app.dependency_overrides.clear()
        self.client = TestClient(app)
        self.admin_user = self._seed_internal_admin()
        self._override_auth_context()

    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def _seed_internal_admin(self) -> User:
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
        async def _auth_context_override():
            # Seed a system tenant in the DB so the admin has a valid tenant
            system_tenant = Tenant(name="System", slug="system", timezone="UTC")
            with SessionLocal() as db:
                db.add(system_tenant)
                db.commit()
                db.refresh(system_tenant)
            return AuthContext(
                user=self.admin_user,
                tenant=system_tenant,
                membership=TenantMembership(
                    tenant_id=system_tenant.id,
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
    # TEST 1: Pre-provisioned user with unique email links correctly
    # ============================================================

    def test_preprovisioned_user_links_sub_on_first_login(self):
        """User pre-provisioned with email and NULL external_auth_id gets linked."""
        user = User(
            email="link-test@test.com",
            name="Preprovisioned User",
            external_auth_id=None,
            is_internal=False,
            status="active",
        )
        with SessionLocal() as db:
            db.add(user)
            db.commit()
            db.refresh(user)
            self.assertIsNone(user.external_auth_id)

            identity = AuthenticatedIdentity(
                external_auth_id="auth0|link123",
                email="link-test@test.com",
                name="Preprovisioned User",
            )
            service = IdentityService(db)
            linked = service.resolve_user(identity)
            self.assertEqual(linked.id, user.id)
            self.assertEqual(linked.external_auth_id, "auth0|link123")

    # ============================================================
    # TEST 2: No duplicate created when email already exists
    # ============================================================

    def test_no_duplicate_when_email_exists(self):
        """Existing user with matching email is returned, not a new one."""
        user = User(
            email="no-dup@test.com",
            name="Existing User",
            external_auth_id=None,
            is_internal=False,
            status="active",
        )
        with SessionLocal() as db:
            db.add(user)
            db.commit()
            db.refresh(user)

            identity = AuthenticatedIdentity(
                external_auth_id="auth0|newsub",
                email="no-dup@test.com",
                name="Existing User",
            )
            service = IdentityService(db)
            resolved = service.resolve_user(identity)
            self.assertEqual(resolved.id, user.id)
            self.assertEqual(resolved.external_auth_id, "auth0|newsub")

            # Verify only one user exists
            count = db.query(User).filter(User.email == "no-dup@test.com").count()
            self.assertEqual(count, 1)

    # ============================================================
    # TEST 3: external_auth_id match always takes priority
    # ============================================================

    def test_external_auth_id_match_takes_priority(self):
        """If external_auth_id matches, that user is returned regardless of email."""
        user_a = User(
            email="user-a@test.com",
            name="User A",
            external_auth_id="auth0|matched",
            is_internal=False,
            status="active",
        )
        user_b = User(
            email="user-b@test.com",
            name="User B",
            external_auth_id=None,
            is_internal=False,
            status="active",
        )
        with SessionLocal() as db:
            db.add(user_a)
            db.add(user_b)
            db.commit()

            # Login with external_auth_id that matches user_a
            identity = AuthenticatedIdentity(
                external_auth_id="auth0|matched",
                email="user-a@test.com",
                name="User A Correct",
            )
            service = IdentityService(db)
            resolved = service.resolve_user(identity)
            self.assertEqual(resolved.id, user_a.id)
            self.assertEqual(resolved.external_auth_id, "auth0|matched")

    # ============================================================
    # TEST 4: Ambiguity (multiple users with same email) fails explicitly
    # ============================================================

    def test_ambiguity_multiple_users_same_email_fails(self):
        """Multiple active users with same email must raise 409.

        Since SQLite enforces UNIQUE(email) at the DB level, we test the
        ambiguity detection by mocking the query to return 2 users.
        """
        user1 = User(
            id=str(uuid.uuid4()),
            email="ambiguous@test.com",
            name="Ambiguous 1",
            external_auth_id=None,
            is_internal=False,
            status="active",
        )
        user2 = User(
            id=str(uuid.uuid4()),
            email="ambiguous@test.com",
            name="Ambiguous 2",
            external_auth_id="auth0|other",
            is_internal=False,
            status="active",
        )

        identity = AuthenticatedIdentity(
            external_auth_id="auth0|new",
            email="ambiguous@test.com",
            name="Trying to Login",
        )

        with SessionLocal() as db:
            # Mock scalars() to return 2 users for email query
            original_scalars = db.scalars

            def mock_scalars(query, *args, **kwargs):
                # Check if this is the email query
                from sqlalchemy.sql import sqltypes

                stmt = query._raw_sql if hasattr(query, "_raw_sql") else str(query)
                if "ambiguous@test.com" in stmt or "email" in str(query):
                    class MockResult:
                        def all(self):
                            return [user1, user2]
                    return MockResult()
                return original_scalars(query, *args, **kwargs)

            db.scalars = mock_scalars

            service = IdentityService(db)
            with self.assertRaises(HTTPException) as ctx:
                service.resolve_user(identity)
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertIn("Multiple active users", ctx.exception.detail)

    # ============================================================
    # TEST 5: No duplicate external_auth_id (non-null)
    # ============================================================

    def test_no_duplicate_external_auth_id_non_null(self):
        """Two users cannot share the same non-null external_auth_id."""
        user = User(
            email="dup-sub@test.com",
            name="User with sub",
            external_auth_id="auth0|dups",
            is_internal=False,
            status="active",
        )
        with SessionLocal() as db:
            db.add(user)
            db.commit()

            # Try to create another user with the same external_auth_id
            new_user = User(
                email="dup-sub-2@test.com",
                name="User 2",
                external_auth_id="auth0|dups",
                is_internal=False,
                status="active",
            )
            db.add(new_user)
            with self.assertRaises(Exception):
                db.commit()

    # ============================================================
    # TEST 6: Tenant/admin creation still works
    # ============================================================

    def test_create_tenant_still_works(self):
        """Tenant creation flow is not broken by identity changes."""
        slug = f"tenant-{uuid.uuid4().hex[:8]}"
        response = self.client.post(
            "/api/v1/admin/tenants",
            json=self._make_admin_payload(slug, agent_count=1),
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["slug"], slug)
        self.assertTrue(data["is_ready_for_calls"])
        self.assertEqual(len(data["agents"]), 1)

    # ============================================================
    # TEST 7: /api/v1/me still works (no regression)
    # ============================================================

    def test_me_endpoint_still_works(self):
        """GET /api/v1/me returns correct data after identity changes."""
        response = self.client.get("/api/v1/me")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["email"], "admin@test.com")
        self.assertTrue(data["is_internal"])
        self.assertIsNotNone(data["tenant_id"])

    # ============================================================
    # TEST 8: Pre-provisioned user without external_auth_id is nullable
    # ============================================================

    def test_nullable_external_auth_id_column(self):
        """Users can be created with external_auth_id = NULL."""
        user = User(
            email=f"nullable-{uuid.uuid4().hex[:6]}@test.com",
            name="Nullable User",
            external_auth_id=None,
            is_internal=False,
            status="active",
        )
        with SessionLocal() as db:
            db.add(user)
            db.commit()
            db.refresh(user)
            self.assertIsNotNone(user.id)
            self.assertIsNone(user.external_auth_id)

    # ============================================================
    # TEST 9: User with external_auth_id already set is not overwritten
    # ============================================================

    def test_existing_external_auth_id_not_overwritten(self):
        """If user already has external_auth_id, it is preserved."""
        user = User(
            email="existing-linked@test.com",
            name="Linked User",
            external_auth_id="auth0|original",
            is_internal=False,
            status="active",
        )
        with SessionLocal() as db:
            db.add(user)
            db.commit()
            db.refresh(user)

            identity = AuthenticatedIdentity(
                external_auth_id="auth0|original",
                email="existing-linked@test.com",
                name="Updated Name",
            )
            service = IdentityService(db)
            resolved = service.resolve_user(identity)
            self.assertEqual(resolved.external_auth_id, "auth0|original")
            self.assertEqual(resolved.name, "Updated Name")  # name is updated

    # ============================================================
    # TEST 10: New user created when no email match
    # ============================================================

    def test_new_user_created_when_no_match(self):
        """When no user matches email or external_auth_id, a new one is created."""
        identity = AuthenticatedIdentity(
            external_auth_id="auth0|brandnew",
            email="brandnew@test.com",
            name="Brand New",
        )
        with SessionLocal() as db:
            service = IdentityService(db)
            new_user = service.resolve_user(identity)
            self.assertEqual(new_user.external_auth_id, "auth0|brandnew")
            self.assertEqual(new_user.email, "brandnew@test.com")

    # ============================================================
    # TEST 11: Admin guard still works
    # ============================================================

    def test_admin_guard_rejects_non_internal(self):
        """Non-internal users get 403 on admin endpoints."""
        non_internal = User(
            email=f"external-{uuid.uuid4().hex[:6]}@test.com",
            name="External",
            is_internal=False,
            external_auth_id="auth0|ext",
        )
        async def _override():
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
        app.dependency_overrides[get_current_auth_context] = _override
        response = self.client.get("/api/v1/admin/tenants")
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
