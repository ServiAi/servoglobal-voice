"""Sprint 7A: Multitenant Onboarding + Identity Risk Fix — comprehensive tests."""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
import unittest

import sqlalchemy as sa
from sqlalchemy import select

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
TEST_DB_PATH = Path("serviai_sprint7a_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.auth.deps import AuthContext, get_current_auth_context
from app.api.endpoints.admin.tenants import get_auth0_provisioning_service
from app.core.config import settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.analytics import Agent, Call, CallEvent, MetricSnapshotDaily
from app.models.identity import AccessAuditLog, Tenant, TenantMembership, User
from app.services.auth0_service import AuthenticatedIdentity
from app.services.auth0_provisioning_service import (
    Auth0ProvisionedUser,
    Auth0ProvisioningError,
    Auth0ProvisioningService,
)
from app.services.identity_service import IdentityService
from app.services.onboarding_service import OnboardingConsistencyError, OnboardingService


class FakeAuth0ProvisioningService:
    def __init__(self) -> None:
        self.created: list[dict[str, str]] = []
        self.deleted: list[str] = []
        self.fail_on_provision: Auth0ProvisioningError | None = None
        self.fail_on_delete: Auth0ProvisioningError | None = None

    def provision_tenant_admin(self, *, email: str, name: str) -> Auth0ProvisionedUser:
        if self.fail_on_provision is not None:
            raise self.fail_on_provision

        user_id = f"auth0|tenant-admin-{len(self.created) + 1}"
        self.created.append({"email": email, "name": name, "user_id": user_id})
        return Auth0ProvisionedUser(
            user_id=user_id,
            email=email,
            name=name,
            connection="Username-Password-Authentication",
            verification_email_sent=True,
            password_reset_triggered=True,
        )

    def delete_user(self, user_id: str) -> None:
        if self.fail_on_delete is not None:
            raise self.fail_on_delete
        self.deleted.append(user_id)


class FakeAuth0Response:
    def __init__(
        self,
        status_code: int,
        payload: dict | None = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("No JSON body")
        return self._payload


class RecordingAuth0HttpClient:
    def __init__(
        self,
        *,
        management_token_status: int = 200,
        delete_status: int = 204,
    ) -> None:
        self.posts: list[dict] = []
        self.deletes: list[dict] = []
        self.management_token_status = management_token_status
        self.delete_status = delete_status

    def post(self, url: str, *, json: dict | None = None, headers: dict | None = None):
        self.posts.append({"url": url, "json": json, "headers": headers})
        if url.endswith("/oauth/token"):
            if self.management_token_status != 200:
                return FakeAuth0Response(
                    self.management_token_status,
                    {
                        "error": "access_denied",
                        "error_description": "Client is not authorized",
                    },
                )
            return FakeAuth0Response(200, {"access_token": "management-token"})
        if url.endswith("/dbconnections/signup"):
            return FakeAuth0Response(
                200,
                {
                    "_id": "signup-created-user-id",
                    "email": json["email"],
                    "email_verified": False,
                },
            )
        if url.endswith("/api/v2/users"):
            return FakeAuth0Response(
                201,
                {
                    "user_id": "auth0|created-from-management-api",
                    "email": json["email"],
                    "name": json["name"],
                    "email_verified": False,
                },
            )
        if url.endswith("/api/v2/jobs/verification-email"):
            return FakeAuth0Response(
                201,
                {"status": "pending", "type": "verification_email", "id": "job_1"},
            )
        if url.endswith("/dbconnections/change_password"):
            return FakeAuth0Response(200, {}, "Password reset email sent")
        raise AssertionError(f"Unexpected POST URL: {url}")

    def delete(self, url: str, *, headers: dict | None = None):
        self.deletes.append({"url": url, "headers": headers})
        return FakeAuth0Response(self.delete_status)


class FakeAuth0Settings:
    AUTH0_DOMAIN = ""
    AUTH0_CLIENT_ID = ""
    AUTH0_CLIENT_SECRET = ""
    AUTH0_MANAGEMENT_DOMAIN = "example.auth0.com"
    AUTH0_MANAGEMENT_CLIENT_ID = "management-client-id"
    AUTH0_MANAGEMENT_CLIENT_SECRET = "management-client-secret"
    AUTH0_MANAGEMENT_AUDIENCE = ""
    AUTH0_ONBOARDING_CONNECTION = "Username-Password-Authentication"
    AUTH0_ONBOARDING_APP_CLIENT_ID = "app-client-id"
    AUTH0_ONBOARDING_SEND_VERIFICATION_EMAIL = True
    AUTH0_ONBOARDING_TRIGGER_PASSWORD_RESET = True
    AUTH0_ONBOARDING_ALLOW_AUTHENTICATION_SIGNUP_FALLBACK = True


class LegacyFallbackAuth0Settings:
    AUTH0_DOMAIN = "fallback.auth0.com"
    AUTH0_CLIENT_ID = "legacy-client-id"
    AUTH0_CLIENT_SECRET = "legacy-client-secret"
    AUTH0_MANAGEMENT_DOMAIN = ""
    AUTH0_MANAGEMENT_CLIENT_ID = ""
    AUTH0_MANAGEMENT_CLIENT_SECRET = ""
    AUTH0_MANAGEMENT_AUDIENCE = ""
    AUTH0_ONBOARDING_CONNECTION = ""
    AUTH0_ONBOARDING_APP_CLIENT_ID = ""
    AUTH0_ONBOARDING_SEND_VERIFICATION_EMAIL = True
    AUTH0_ONBOARDING_TRIGGER_PASSWORD_RESET = True
    AUTH0_ONBOARDING_ALLOW_AUTHENTICATION_SIGNUP_FALLBACK = True


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
        self.auth0_provisioning = FakeAuth0ProvisioningService()
        app.dependency_overrides[get_auth0_provisioning_service] = (
            lambda: self.auth0_provisioning
        )
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
            with SessionLocal() as db:
                system_tenant = db.scalar(
                    select(Tenant).where(Tenant.slug == "system")
                )
                if system_tenant is None:
                    system_tenant = Tenant(name="System", slug="system", timezone="UTC")
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
                email_verified=True,
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
                email_verified=True,
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
                email_verified=True,
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
            email_verified=True,
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
        self.assertEqual(data["admin"]["external_auth_id"], "auth0|tenant-admin-1")
        self.assertTrue(data["admin"]["has_auth0_link"])
        self.assertTrue(
            data["admin"]["auth0_provisioning"]["verification_email_sent"]
        )
        self.assertTrue(
            data["admin"]["auth0_provisioning"]["password_reset_triggered"]
        )
        self.assertEqual(self.auth0_provisioning.created[0]["email"], data["admin"]["email"])

    def test_create_tenant_reuses_preprovisioned_admin_user(self):
        """Tenant creation links an unlinked admin user instead of duplicating email."""
        slug = f"tenant-{uuid.uuid4().hex[:8]}"
        email = f"preprovisioned-{uuid.uuid4().hex[:6]}@agency.com"
        with SessionLocal() as db:
            existing_user = User(
                email=email,
                name="Preprovisioned Admin",
                external_auth_id=None,
                is_internal=False,
                status="active",
            )
            db.add(existing_user)
            db.commit()
            db.refresh(existing_user)
            existing_user_id = existing_user.id

        payload = self._make_admin_payload(slug)
        payload["admin"]["email"] = email
        payload["admin"]["name"] = "Tenant Admin"

        response = self.client.post("/api/v1/admin/tenants", json=payload)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["admin"]["id"], existing_user_id)
        self.assertEqual(data["admin"]["email"], email)
        self.assertEqual(data["admin"]["external_auth_id"], "auth0|tenant-admin-1")
        with SessionLocal() as db:
            count = db.query(User).filter(User.email == email).count()
            self.assertEqual(count, 1)
            linked = db.scalar(select(User).where(User.email == email))
            self.assertEqual(linked.external_auth_id, "auth0|tenant-admin-1")

    def test_create_tenant_does_not_duplicate_linked_admin_email(self):
        """Existing linked admin email is rejected before any Auth0 provisioning call."""
        slug = f"tenant-{uuid.uuid4().hex[:8]}"
        email = f"linked-{uuid.uuid4().hex[:6]}@agency.com"
        with SessionLocal() as db:
            existing_user = User(
                email=email,
                name="Linked Admin",
                external_auth_id="auth0|already-linked",
                is_internal=False,
                status="active",
            )
            db.add(existing_user)
            db.commit()

        payload = self._make_admin_payload(slug)
        payload["admin"]["email"] = email

        response = self.client.post("/api/v1/admin/tenants", json=payload)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.auth0_provisioning.created, [])

    def test_create_tenant_auth0_failure_leaves_no_local_tenant(self):
        """If Auth0 provisioning fails, no tenant/user/membership is persisted."""
        slug = f"tenant-{uuid.uuid4().hex[:8]}"
        payload = self._make_admin_payload(slug)
        email = payload["admin"]["email"]
        self.auth0_provisioning.fail_on_provision = Auth0ProvisioningError(
            "Auth0 unavailable",
            status_code=500,
        )

        response = self.client.post("/api/v1/admin/tenants", json=payload)

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "Auth0 unavailable")
        with SessionLocal() as db:
            self.assertIsNone(db.scalar(select(Tenant).where(Tenant.slug == slug)))
            self.assertIsNone(db.scalar(select(User).where(User.email == email)))

    def test_auth0_user_is_deleted_when_local_creation_fails(self):
        """If local DB creation fails after Auth0 creation, compensation deletes Auth0 user."""
        slug = f"tenant-{uuid.uuid4().hex[:8]}"
        email = f"broken-{uuid.uuid4().hex[:6]}@agency.com"
        fake_auth0 = FakeAuth0ProvisioningService()

        with SessionLocal() as db:
            service = OnboardingService(db, fake_auth0)
            with self.assertRaises(OnboardingConsistencyError) as ctx:
                service.create_tenant(
                    name="Broken Agency",
                    slug=slug,
                    admin_name="Broken Admin",
                    admin_email=email,
                    agents=[
                        {
                            "name": "Broken Agent",
                            "external_provider": "ultravox",
                        }
                    ],
                )

        self.assertTrue(ctx.exception.compensation_attempted)
        self.assertTrue(ctx.exception.compensation_succeeded)
        self.assertEqual(fake_auth0.deleted, ["auth0|tenant-admin-1"])
        with SessionLocal() as db:
            self.assertIsNone(db.scalar(select(Tenant).where(Tenant.slug == slug)))
            self.assertIsNone(db.scalar(select(User).where(User.email == email)))

    def test_auth0_provisioning_service_invokes_verification_and_password_reset(self):
        """Enabled activation flags call Auth0 verification job and password reset flows."""
        http_client = RecordingAuth0HttpClient()
        service = Auth0ProvisioningService(
            http_client=http_client,
            settings_obj=FakeAuth0Settings,
        )

        provisioned = service.provision_tenant_admin(
            email="new-admin@agency.com",
            name="New Admin",
        )

        self.assertEqual(provisioned.user_id, "auth0|created-from-management-api")
        self.assertTrue(provisioned.verification_email_sent)
        self.assertTrue(provisioned.password_reset_triggered)
        post_urls = [call["url"] for call in http_client.posts]
        self.assertIn("https://example.auth0.com/oauth/token", post_urls)
        self.assertIn("https://example.auth0.com/api/v2/users", post_urls)
        self.assertIn(
            "https://example.auth0.com/api/v2/jobs/verification-email",
            post_urls,
        )
        create_payload = next(
            (call["json"] for call in http_client.posts if "api/v2/users" in call["url"]),
            {},
        )
        self.assertFalse(
            create_payload.get("verify_email"),
            "verification is sent explicitly through Auth0 jobs",
        )
        verification_payload = next(
            (
                call["json"]
                for call in http_client.posts
                if "api/v2/jobs/verification-email" in call["url"]
            ),
            {},
        )
        self.assertEqual(
            verification_payload.get("user_id"),
            "auth0|created-from-management-api",
        )
        self.assertIn(
            "https://example.auth0.com/dbconnections/change_password",
            post_urls,
        )

    def test_auth0_provisioning_service_uses_legacy_auth0_fallbacks(self):
        """Staging can provision when management-specific env vars are absent."""
        http_client = RecordingAuth0HttpClient()
        service = Auth0ProvisioningService(
            http_client=http_client,
            settings_obj=LegacyFallbackAuth0Settings,
        )

        provisioned = service.provision_tenant_admin(
            email="fallback-admin@agency.com",
            name="Fallback Admin",
        )

        self.assertEqual(provisioned.connection, "Username-Password-Authentication")
        token_request = next(
            call for call in http_client.posts if call["url"].endswith("/oauth/token")
        )
        self.assertEqual(token_request["json"]["client_id"], "legacy-client-id")
        self.assertEqual(token_request["json"]["client_secret"], "legacy-client-secret")
        self.assertEqual(
            token_request["json"]["audience"],
            "https://fallback.auth0.com/api/v2/",
        )
        password_reset_request = next(
            call
            for call in http_client.posts
            if call["url"].endswith("/dbconnections/change_password")
        )
        self.assertEqual(password_reset_request["json"]["client_id"], "legacy-client-id")
        self.assertEqual(
            password_reset_request["json"]["connection"],
            "Username-Password-Authentication",
        )

    def test_auth0_provisioning_service_falls_back_to_authentication_signup(self):
        """If Management API is not authorized, create a real DB user via signup."""
        http_client = RecordingAuth0HttpClient(management_token_status=403)
        service = Auth0ProvisioningService(
            http_client=http_client,
            settings_obj=LegacyFallbackAuth0Settings,
        )

        provisioned = service.provision_tenant_admin(
            email="fallback-signup@agency.com",
            name="Fallback Signup",
        )

        self.assertEqual(provisioned.user_id, "auth0|signup-created-user-id")
        self.assertEqual(provisioned.created_via, "authentication_api_signup")
        self.assertFalse(provisioned.verification_email_sent)
        self.assertTrue(provisioned.password_reset_triggered)
        self.assertTrue(provisioned.activation_errors)
        self.assertIn(
            "Failed to get Auth0 Management API token",
            provisioned.activation_errors[0],
        )
        post_urls = [call["url"] for call in http_client.posts]
        self.assertIn("https://fallback.auth0.com/dbconnections/signup", post_urls)
        self.assertNotIn("https://fallback.auth0.com/api/v2/users", post_urls)

    def test_auth0_delete_user_treats_missing_user_as_success(self):
        """Auth0 404 means the external user is already absent."""
        http_client = RecordingAuth0HttpClient(delete_status=404)
        service = Auth0ProvisioningService(
            http_client=http_client,
            settings_obj=FakeAuth0Settings,
        )

        service.delete_user("auth0|already-deleted")

        self.assertEqual(len(http_client.deletes), 1)
        self.assertIn("auth0%7Calready-deleted", http_client.deletes[0]["url"])

    def test_delete_tenant_removes_tenant_owned_records_and_users(self):
        """Deleting a tenant removes tenant data and tenant-only identity users."""
        slug = f"tenant-{uuid.uuid4().hex[:8]}"
        payload = self._make_admin_payload(slug, agent_count=1)
        email = payload["admin"]["email"]
        created = self.client.post("/api/v1/admin/tenants", json=payload)
        self.assertEqual(created.status_code, 201)
        tenant_id = created.json()["id"]

        with SessionLocal() as db:
            admin_user = db.scalar(select(User).where(User.email == email))
            agent = db.scalar(select(Agent).where(Agent.tenant_id == tenant_id))
            self.assertIsNotNone(admin_user)
            self.assertIsNotNone(agent)
            admin_external_auth_id = admin_user.external_auth_id

            call = Call(
                tenant_id=tenant_id,
                external_call_id=f"call-{uuid.uuid4().hex[:8]}",
                external_provider="ultravox",
                agent_id=agent.id,
                provider_agent_id=agent.external_agent_id,
                normalized_status="answered",
                started_at=datetime.now(UTC),
                duration_seconds=42,
                billed_minutes=Decimal("0.70"),
            )
            db.add(call)
            db.flush()
            db.add(
                CallEvent(
                    call_id=call.id,
                    tenant_id=tenant_id,
                    event_type="call.ended",
                    payload_json={"ok": True},
                )
            )
            db.add(
                MetricSnapshotDaily(
                    tenant_id=tenant_id,
                    agent_id=agent.id,
                    date=date.today(),
                    calls_total=1,
                    calls_answered=1,
                    calls_unanswered=0,
                    duration_total_seconds=42,
                    billed_minutes=Decimal("0.70"),
                )
            )
            db.add(
                AccessAuditLog(
                    user_id=admin_user.id,
                    tenant_id=tenant_id,
                    action="tenant.delete.test",
                )
            )
            db.commit()

        deleted = self.client.delete(f"/api/v1/admin/tenants/{tenant_id}")

        self.assertEqual(deleted.status_code, 200)
        data = deleted.json()
        self.assertTrue(data["deleted"])
        self.assertEqual(data["deleted_counts"]["users"], 1)
        self.assertEqual(data["deleted_counts"]["auth0_users"], 1)
        self.assertEqual(data["deleted_counts"]["tenants"], 1)
        self.assertEqual(self.auth0_provisioning.deleted, [admin_external_auth_id])

        with SessionLocal() as db:
            self.assertIsNone(db.scalar(select(Tenant).where(Tenant.id == tenant_id)))
            self.assertEqual(
                db.query(TenantMembership)
                .filter(TenantMembership.tenant_id == tenant_id)
                .count(),
                0,
            )
            self.assertEqual(db.query(Agent).filter(Agent.tenant_id == tenant_id).count(), 0)
            self.assertEqual(db.query(Call).filter(Call.tenant_id == tenant_id).count(), 0)
            self.assertEqual(
                db.query(CallEvent).filter(CallEvent.tenant_id == tenant_id).count(),
                0,
            )
            self.assertEqual(
                db.query(MetricSnapshotDaily)
                .filter(MetricSnapshotDaily.tenant_id == tenant_id)
                .count(),
                0,
            )
            self.assertEqual(
                db.query(AccessAuditLog)
                .filter(AccessAuditLog.tenant_id == tenant_id)
                .count(),
                0,
            )
            self.assertIsNone(db.scalar(select(User).where(User.email == email)))

    def test_delete_tenant_auth0_failure_blocks_local_deletion(self):
        """Auth0 delete failures preserve local records for retry."""
        slug = f"tenant-{uuid.uuid4().hex[:8]}"
        payload = self._make_admin_payload(slug, agent_count=0)
        email = payload["admin"]["email"]
        created = self.client.post("/api/v1/admin/tenants", json=payload)
        self.assertEqual(created.status_code, 201)
        tenant_id = created.json()["id"]
        self.auth0_provisioning.fail_on_delete = Auth0ProvisioningError(
            "Auth0 delete failed",
            status_code=403,
        )

        deleted = self.client.delete(f"/api/v1/admin/tenants/{tenant_id}")

        self.assertEqual(deleted.status_code, 502)
        self.assertEqual(deleted.json()["detail"], "Auth0 delete failed")
        with SessionLocal() as db:
            self.assertIsNotNone(db.scalar(select(Tenant).where(Tenant.id == tenant_id)))
            self.assertIsNotNone(db.scalar(select(User).where(User.email == email)))

    def test_delete_bootstrap_tenant_is_blocked(self):
        """Bootstrap tenant cannot be deleted from the admin console."""
        payload = self._make_admin_payload(settings.BOOTSTRAP_TENANT_SLUG, agent_count=0)
        payload["name"] = settings.BOOTSTRAP_TENANT_NAME
        email = payload["admin"]["email"]
        created = self.client.post("/api/v1/admin/tenants", json=payload)
        self.assertEqual(created.status_code, 201)
        tenant_id = created.json()["id"]

        deleted = self.client.delete(f"/api/v1/admin/tenants/{tenant_id}")

        self.assertEqual(deleted.status_code, 409)
        self.assertIn("bootstrap tenant", deleted.json()["detail"])
        with SessionLocal() as db:
            self.assertIsNotNone(db.scalar(select(Tenant).where(Tenant.id == tenant_id)))
            self.assertIsNotNone(db.scalar(select(User).where(User.email == email)))

    def test_delete_missing_tenant_returns_404(self):
        response = self.client.delete(f"/api/v1/admin/tenants/{uuid.uuid4()}")
        self.assertEqual(response.status_code, 404)

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
                email_verified=True,
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
            email_verified=True,
        )
        with SessionLocal() as db:
            service = IdentityService(db)
            new_user = service.resolve_user(identity)
            self.assertEqual(new_user.external_auth_id, "auth0|brandnew")
            self.assertEqual(new_user.email, "brandnew@test.com")

    # ============================================================
    # TEST 12: Email verification blocks unverified login
    # ============================================================

    def test_unverified_email_blocks_login(self):
        """Login is blocked when Auth0 reports email_verified=false."""
        user = User(
            email="unverified@test.com",
            name="Unverified User",
            external_auth_id="auth0|unverified",
            is_internal=False,
            status="active",
        )
        with SessionLocal() as db:
            db.add(user)
            db.commit()
            db.refresh(user)

            identity = AuthenticatedIdentity(
                external_auth_id="auth0|unverified",
                email="unverified@test.com",
                name="Unverified User",
                email_verified=False,
            )
            service = IdentityService(db)
            with self.assertRaises(HTTPException) as ctx:
                service.resolve_user(identity)
            self.assertEqual(ctx.exception.status_code, 403)
            self.assertIn("Email not verified", ctx.exception.detail)

    def test_unverified_email_blocks_email_match_login(self):
        """Login by email match is also blocked when email_verified=false."""
        user = User(
            email="unverified-by-email@test.com",
            name="Unverified By Email",
            external_auth_id=None,
            is_internal=False,
            status="active",
        )
        with SessionLocal() as db:
            db.add(user)
            db.commit()
            db.refresh(user)

            identity = AuthenticatedIdentity(
                external_auth_id="auth0|newsub2",
                email="unverified-by-email@test.com",
                name="Unverified By Email",
                email_verified=False,
            )
            service = IdentityService(db)
            with self.assertRaises(HTTPException) as ctx:
                service.resolve_user(identity)
            self.assertEqual(ctx.exception.status_code, 403)
            self.assertIn("Email not verified", ctx.exception.detail)

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

    # ============================================================
    # TEST 12: Tenant memberships management
    # ============================================================

    def test_add_membership_with_new_email_preprovisions_user(self):
        """Adding a membership with an email not previously registered pre-provisions the user."""
        slug = f"tenant-{uuid.uuid4().hex[:8]}"
        created = self.client.post(
            "/api/v1/admin/tenants",
            json=self._make_admin_payload(slug, agent_count=0),
        )
        self.assertEqual(created.status_code, 201)
        tenant_id = created.json()["id"]

        new_email = f"new-member-{uuid.uuid4().hex[:6]}@example.com"
        response = self.client.post(
            f"/api/v1/admin/tenants/{tenant_id}/memberships",
            json={"email": new_email, "role": "tenant_analyst"},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["user_email"], new_email)
        self.assertEqual(data["role"], "tenant_analyst")
        self.assertEqual(data["status"], "active")

        # Verify pre-provisioned user in DB
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == new_email))
            self.assertIsNotNone(user)
            self.assertIsNone(user.external_auth_id)
            self.assertEqual(user.status, "active")

            membership = db.scalar(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == tenant_id,
                    TenantMembership.user_id == user.id,
                )
            )
            self.assertIsNotNone(membership)
            self.assertEqual(membership.role, "tenant_analyst")

    def test_add_membership_with_existing_user_reuses_user(self):
        """Adding a membership for an existing user reuses the user and creates the membership."""
        slug = f"tenant-{uuid.uuid4().hex[:8]}"
        created = self.client.post(
            "/api/v1/admin/tenants",
            json=self._make_admin_payload(slug, agent_count=0),
        )
        self.assertEqual(created.status_code, 201)
        tenant_id = created.json()["id"]

        existing_email = f"existing-{uuid.uuid4().hex[:6]}@example.com"
        with SessionLocal() as db:
            existing_user = User(
                email=existing_email,
                name="Existing User",
                is_internal=False,
                status="active",
            )
            db.add(existing_user)
            db.commit()
            existing_user_id = existing_user.id

        response = self.client.post(
            f"/api/v1/admin/tenants/{tenant_id}/memberships",
            json={"email": existing_email, "role": "tenant_admin"},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["user_id"], existing_user_id)
        self.assertEqual(data["user_email"], existing_email)

    def test_add_membership_duplicate_raises_409(self):
        """Adding a duplicate membership for the same user in the tenant returns 409 Conflict."""
        slug = f"tenant-{uuid.uuid4().hex[:8]}"
        created = self.client.post(
            "/api/v1/admin/tenants",
            json=self._make_admin_payload(slug, agent_count=0),
        )
        self.assertEqual(created.status_code, 201)
        tenant_id = created.json()["id"]

        email = f"dup-member-{uuid.uuid4().hex[:6]}@example.com"
        first = self.client.post(
            f"/api/v1/admin/tenants/{tenant_id}/memberships",
            json={"email": email, "role": "tenant_analyst"},
        )
        self.assertEqual(first.status_code, 201)

        second = self.client.post(
            f"/api/v1/admin/tenants/{tenant_id}/memberships",
            json={"email": email, "role": "tenant_admin"},
        )
        self.assertEqual(second.status_code, 409)
        self.assertIn("already has a membership", second.json()["detail"])

    def test_add_membership_unknown_tenant_raises_404(self):
        """Adding a membership to an unknown tenant returns 404 Not Found."""
        unknown_id = str(uuid.uuid4())
        response = self.client.post(
            f"/api/v1/admin/tenants/{unknown_id}/memberships",
            json={"email": "test@example.com", "role": "tenant_analyst"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn(f"Tenant '{unknown_id}' not found", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
