from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")
os.environ["SERVIAI_TEST_SECRET_FALLBACK"] = "1"
TEST_DB_PATH = Path("serviai_tenant_features_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext, get_current_auth_context
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.identity import Tenant, TenantMembership, User
from app.models.tenant_features import TenantFeatureGrant
from app.services.tenant_feature_service import (
    AGENT_BUILDER,
    TenantFeatureService,
    TenantFeatureDisabledError,
    UnknownTenantFeatureError,
    VOICE_EXPERIENCES,
    WHATSAPP_BUSINESS_CALLING,
    _UNIQUE_CONSTRAINT_NAME,
    _is_feature_grant_unique_violation,
)


class TenantFeatureTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        engine.dispose()
        TEST_DB_PATH.unlink(missing_ok=True)

    def setUp(self) -> None:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        app.dependency_overrides.clear()
        ids = self._seed_data()
        self.tenant_a_id = ids["tenant_a_id"]
        self.tenant_b_id = ids["tenant_b_id"]
        self.internal_user_id = ids["internal_user_id"]
        self.platform_admin_user_id = ids["platform_admin_user_id"]
        self.tenant_admin_user_id = ids["tenant_admin_user_id"]
        self.tenant_analyst_user_id = ids["tenant_analyst_user_id"]
        self.tenant_viewer_user_id = ids["tenant_viewer_user_id"]
        # Default actor is the internal platform user: most tests exercise the
        # happy path, only the dedicated authorization tests switch actors.
        self.current_user_id = self.internal_user_id
        app.dependency_overrides[get_current_auth_context] = self._auth_context_override
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def _seed_data(self) -> dict:
        with SessionLocal() as db:
            tenant_a = Tenant(name="Tenant A", slug="tenant-a")
            tenant_b = Tenant(name="Tenant B", slug="tenant-b")
            internal_user = User(
                email="internal@example.com",
                name="Internal Staff",
                status="active",
                is_internal=True,
            )
            platform_admin_user = User(
                email="platform@example.com",
                name="Platform Admin",
                status="active",
                is_internal=False,
            )
            tenant_admin_user = User(
                email="tenant-admin@example.com",
                name="Tenant Admin",
                status="active",
                is_internal=False,
            )
            tenant_analyst_user = User(
                email="tenant-analyst@example.com",
                name="Tenant Analyst",
                status="active",
                is_internal=False,
            )
            tenant_viewer_user = User(
                email="tenant-viewer@example.com",
                name="Tenant Viewer",
                status="active",
                is_internal=False,
            )
            db.add_all(
                [
                    tenant_a,
                    tenant_b,
                    internal_user,
                    platform_admin_user,
                    tenant_admin_user,
                    tenant_analyst_user,
                    tenant_viewer_user,
                ]
            )
            db.flush()
            # All actors hold their membership on tenant_a. Internal-user tests
            # then operate on tenant_b on purpose, to prove authorization does
            # not depend on the context tenant matching the path tenant_id.
            db.add_all(
                [
                    TenantMembership(
                        tenant_id=tenant_a.id,
                        user_id=internal_user.id,
                        role="platform_admin",
                        status="active",
                    ),
                    TenantMembership(
                        tenant_id=tenant_a.id,
                        user_id=platform_admin_user.id,
                        role="platform_admin",
                        status="active",
                    ),
                    TenantMembership(
                        tenant_id=tenant_a.id,
                        user_id=tenant_admin_user.id,
                        role="tenant_admin",
                        status="active",
                    ),
                    TenantMembership(
                        tenant_id=tenant_a.id,
                        user_id=tenant_analyst_user.id,
                        role="tenant_analyst",
                        status="active",
                    ),
                    TenantMembership(
                        tenant_id=tenant_a.id,
                        user_id=tenant_viewer_user.id,
                        role="tenant_viewer",
                        status="active",
                    ),
                ]
            )
            db.commit()
            return {
                "tenant_a_id": tenant_a.id,
                "tenant_b_id": tenant_b.id,
                "internal_user_id": internal_user.id,
                "platform_admin_user_id": platform_admin_user.id,
                "tenant_admin_user_id": tenant_admin_user.id,
                "tenant_analyst_user_id": tenant_analyst_user.id,
                "tenant_viewer_user_id": tenant_viewer_user.id,
            }

    async def _auth_context_override(self) -> AuthContext:
        with SessionLocal() as db:
            user = db.get(User, self.current_user_id)
            membership = db.scalar(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == self.tenant_a_id,
                    TenantMembership.user_id == self.current_user_id,
                )
            )
            return AuthContext(
                user=user,
                tenant=db.get(Tenant, self.tenant_a_id),
                membership=membership,
            )

    @staticmethod
    def _payload(enabled: bool = True) -> dict:
        return {
            "enabled": enabled,
            "limits": {"max_experiences": 5, "max_context_fields": 20},
        }

    def _get(self, tenant_id: str):
        return self.client.get(f"/api/v1/admin/tenants/{tenant_id}/features")

    def _put(self, tenant_id: str, payload: dict | None = None):
        return self.client.put(
            f"/api/v1/admin/tenants/{tenant_id}/features/voice-experiences",
            json=payload or self._payload(),
        )

    def _put_calling(self, tenant_id: str, enabled: bool = True):
        return self.client.put(
            f"/api/v1/admin/tenants/{tenant_id}/features/whatsapp-business-calling",
            json={"enabled": enabled},
        )

    def _put_agent_builder(self, tenant_id: str, enabled: bool = True):
        return self.client.put(
            f"/api/v1/admin/tenants/{tenant_id}/features/agent-builder-v2",
            json={"enabled": enabled},
        )

    # ---- P1: authorization -------------------------------------------------

    def test_internal_user_can_list_features_for_any_tenant(self) -> None:
        # internal_user's own membership is on tenant_a; tenant_b is a
        # different tenant, proving the check does not compare tenants.
        response = self._get(self.tenant_b_id)
        self.assertEqual(response.status_code, 200)

    def test_internal_user_can_configure_features_for_any_tenant(self) -> None:
        response = self._put(self.tenant_b_id)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["enabled"])
        with SessionLocal() as db:
            grant = db.scalar(
                select(TenantFeatureGrant).where(
                    TenantFeatureGrant.tenant_id == self.tenant_b_id
                )
            )
            self.assertEqual(grant.feature_key, VOICE_EXPERIENCES)
            self.assertTrue(grant.enabled)
            self.assertEqual(grant.enabled_by_user_id, self.internal_user_id)

    def test_authorization_does_not_depend_on_context_tenant_matching_path(self) -> None:
        # Same actor as above (context.tenant == tenant_a) succeeding against
        # tenant_b is the explicit regression check for the old tenant-match
        # fallback that used to gate access.
        self.current_user_id = self.internal_user_id
        self.assertEqual(self._get(self.tenant_b_id).status_code, 200)
        self.assertEqual(self._put(self.tenant_b_id).status_code, 200)

    def test_non_internal_platform_admin_role_is_forbidden_on_own_tenant(self) -> None:
        self.current_user_id = self.platform_admin_user_id
        self.assertEqual(self._get(self.tenant_a_id).status_code, 403)
        self.assertEqual(self._put(self.tenant_a_id).status_code, 403)

    def test_tenant_admin_is_forbidden(self) -> None:
        self.current_user_id = self.tenant_admin_user_id
        self.assertEqual(self._get(self.tenant_a_id).status_code, 403)
        self.assertEqual(self._put(self.tenant_a_id).status_code, 403)

    def test_tenant_analyst_is_forbidden(self) -> None:
        self.current_user_id = self.tenant_analyst_user_id
        self.assertEqual(self._get(self.tenant_a_id).status_code, 403)
        self.assertEqual(self._put(self.tenant_a_id).status_code, 403)

    def test_tenant_viewer_is_forbidden(self) -> None:
        self.current_user_id = self.tenant_viewer_user_id
        self.assertEqual(self._get(self.tenant_a_id).status_code, 403)
        self.assertEqual(self._put(self.tenant_a_id).status_code, 403)

    def test_unknown_tenant_is_rejected_for_internal_user(self) -> None:
        self.assertEqual(self._get("missing-tenant").status_code, 404)
        self.assertEqual(self._put("missing-tenant").status_code, 404)

    # ---- Functional behavior (unaffected by P1, kept under the internal actor) --

    def test_update_existing_feature_without_duplicate(self) -> None:
        self.assertEqual(self._put(self.tenant_a_id).status_code, 200)
        response = self._put(
            self.tenant_a_id,
            {
                "enabled": True,
                "limits": {"max_experiences": 8, "max_context_fields": 30},
            },
        )

        self.assertEqual(response.status_code, 200)
        with SessionLocal() as db:
            count = db.scalar(select(func.count()).select_from(TenantFeatureGrant))
            grant = db.scalar(select(TenantFeatureGrant))
            self.assertEqual(count, 1)
            self.assertEqual(grant.limits_json["max_experiences"], 8)

    def test_disabled_feature_is_not_enabled_or_allowed(self) -> None:
        self.assertEqual(self._put(self.tenant_a_id, self._payload(False)).status_code, 200)
        with SessionLocal() as db:
            service = TenantFeatureService(db)
            self.assertFalse(service.is_enabled(self.tenant_a_id, VOICE_EXPERIENCES))
            with self.assertRaises(TenantFeatureDisabledError):
                service.require_enabled(self.tenant_a_id, VOICE_EXPERIENCES)

    def test_unknown_feature_is_rejected(self) -> None:
        with SessionLocal() as db:
            with self.assertRaises(UnknownTenantFeatureError):
                TenantFeatureService(db).set_feature(
                    self.tenant_a_id,
                    "unknown_feature",
                    True,
                    self._payload()["limits"],
                    self.internal_user_id,
                )

    def test_features_are_isolated_between_tenants(self) -> None:
        self.assertEqual(self._put(self.tenant_a_id).status_code, 200)
        self.assertEqual(self._put(self.tenant_b_id, self._payload(False)).status_code, 200)

        tenant_a = self._get(self.tenant_a_id).json()
        tenant_b = self._get(self.tenant_b_id).json()
        self.assertTrue(tenant_a[0]["enabled"])
        self.assertFalse(tenant_b[0]["enabled"])

    def test_limits_are_validated_and_persisted(self) -> None:
        invalid = self._put(
            self.tenant_a_id,
            {
                "enabled": True,
                "limits": {"max_experiences": 0, "max_context_fields": 20},
            },
        )
        valid = self._put(self.tenant_a_id)

        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(valid.status_code, 200)
        with SessionLocal() as db:
            grant = db.scalar(select(TenantFeatureGrant))
            self.assertEqual(
                grant.limits_json,
                {"max_experiences": 5, "max_context_fields": 20},
            )

    def test_response_contains_only_safe_feature_fields(self) -> None:
        response = self._put(self.tenant_a_id)
        payload = response.json()

        self.assertEqual(
            set(payload),
            {"feature_key", "enabled", "limits", "created_at", "updated_at"},
        )
        self.assertNotIn(self.internal_user_id, response.text)
        self.assertNotIn("internal@example.com", response.text)

    # ---- whatsapp_business_calling feature ---------------------------------

    def test_whatsapp_business_calling_can_be_toggled(self) -> None:
        response = self._put_calling(self.tenant_a_id)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["feature_key"], WHATSAPP_BUSINESS_CALLING)
        self.assertTrue(body["enabled"])
        self.assertEqual(body["limits"], {})
        with SessionLocal() as db:
            self.assertTrue(
                TenantFeatureService(db).is_enabled(self.tenant_a_id, WHATSAPP_BUSINESS_CALLING)
            )

    def test_whatsapp_business_calling_is_isolated_between_tenants(self) -> None:
        self.assertEqual(self._put_calling(self.tenant_a_id, True).status_code, 200)
        self.assertEqual(self._put_calling(self.tenant_b_id, False).status_code, 200)

        with SessionLocal() as db:
            service = TenantFeatureService(db)
            self.assertTrue(service.is_enabled(self.tenant_a_id, WHATSAPP_BUSINESS_CALLING))
            self.assertFalse(service.is_enabled(self.tenant_b_id, WHATSAPP_BUSINESS_CALLING))

    # ---- agent_builder_v2 feature -------------------------------------------

    def test_agent_builder_can_be_toggled(self) -> None:
        response = self._put_agent_builder(self.tenant_a_id)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["feature_key"], AGENT_BUILDER)
        self.assertTrue(body["enabled"])
        self.assertEqual(body["limits"], {})
        with SessionLocal() as db:
            self.assertTrue(
                TenantFeatureService(db).is_enabled(self.tenant_a_id, AGENT_BUILDER)
            )

    def test_agent_builder_is_isolated_between_tenants(self) -> None:
        self.assertEqual(self._put_agent_builder(self.tenant_a_id, True).status_code, 200)
        self.assertEqual(self._put_agent_builder(self.tenant_b_id, False).status_code, 200)

        with SessionLocal() as db:
            service = TenantFeatureService(db)
            self.assertTrue(service.is_enabled(self.tenant_a_id, AGENT_BUILDER))
            self.assertFalse(service.is_enabled(self.tenant_b_id, AGENT_BUILDER))

    # ---- P2: IntegrityError handling ---------------------------------------

    def test_concurrent_create_recovers_via_real_unique_violation(self) -> None:
        original_commit = Session.commit
        injected = False

        def racing_commit(session_self, *args, **kwargs):
            nonlocal injected
            if not injected:
                injected = True
                with SessionLocal() as other:
                    other.add(
                        TenantFeatureGrant(
                            tenant_id=self.tenant_a_id,
                            feature_key=VOICE_EXPERIENCES,
                            enabled=False,
                            limits_json={"max_experiences": 1, "max_context_fields": 1},
                        )
                    )
                    other.commit()
            return original_commit(session_self, *args, **kwargs)

        with patch.object(Session, "commit", racing_commit):
            with SessionLocal() as db:
                service = TenantFeatureService(db)
                grant = service.set_feature(
                    self.tenant_a_id,
                    VOICE_EXPERIENCES,
                    True,
                    self._payload()["limits"],
                    self.internal_user_id,
                )
                # the session must remain usable right after recovering
                recount = db.scalar(select(func.count()).select_from(TenantFeatureGrant))
                self.assertEqual(recount, 1)

        self.assertTrue(grant.enabled)
        self.assertEqual(grant.limits_json, self._payload()["limits"])
        self.assertEqual(grant.enabled_by_user_id, self.internal_user_id)
        with SessionLocal() as db:
            count = db.scalar(select(func.count()).select_from(TenantFeatureGrant))
            self.assertEqual(count, 1)

    def test_other_integrity_error_is_reraised_on_create(self) -> None:
        fake_orig = SimpleNamespace(diag=SimpleNamespace(constraint_name="some_other_fk"))
        fake_error = IntegrityError("INSERT", {}, fake_orig)
        with SessionLocal() as db:
            with patch.object(Session, "commit", side_effect=fake_error):
                with self.assertRaises(IntegrityError):
                    TenantFeatureService(db).set_feature(
                        self.tenant_a_id,
                        VOICE_EXPERIENCES,
                        True,
                        self._payload()["limits"],
                        self.internal_user_id,
                    )

    def test_foreign_key_violation_is_not_hidden(self) -> None:
        fake_error = IntegrityError("INSERT", {}, Exception("FOREIGN KEY constraint failed"))
        with SessionLocal() as db:
            with patch.object(Session, "commit", side_effect=fake_error):
                with self.assertRaises(IntegrityError):
                    TenantFeatureService(db).set_feature(
                        self.tenant_a_id,
                        VOICE_EXPERIENCES,
                        True,
                        self._payload()["limits"],
                        self.internal_user_id,
                    )

    def test_integrity_error_on_update_is_reraised_even_for_matching_constraint(self) -> None:
        with SessionLocal() as db:
            TenantFeatureService(db).set_feature(
                self.tenant_a_id,
                VOICE_EXPERIENCES,
                True,
                self._payload()["limits"],
                self.internal_user_id,
            )

        fake_orig = SimpleNamespace(diag=SimpleNamespace(constraint_name=_UNIQUE_CONSTRAINT_NAME))
        fake_error = IntegrityError("UPDATE", {}, fake_orig)
        with SessionLocal() as db:
            with patch.object(Session, "commit", side_effect=fake_error):
                with self.assertRaises(IntegrityError):
                    TenantFeatureService(db).set_feature(
                        self.tenant_a_id,
                        VOICE_EXPERIENCES,
                        False,
                        self._payload()["limits"],
                        self.internal_user_id,
                    )


class FeatureGrantUniqueViolationDetectionTests(unittest.TestCase):
    def test_detects_postgres_constraint_name(self) -> None:
        orig = SimpleNamespace(diag=SimpleNamespace(constraint_name=_UNIQUE_CONSTRAINT_NAME))
        exc = IntegrityError("INSERT", {}, orig)
        self.assertTrue(_is_feature_grant_unique_violation(exc))

    def test_rejects_different_postgres_constraint_name(self) -> None:
        orig = SimpleNamespace(diag=SimpleNamespace(constraint_name="some_other_fk"))
        exc = IntegrityError("INSERT", {}, orig)
        self.assertFalse(_is_feature_grant_unique_violation(exc))

    def test_detects_sqlite_message_with_exact_columns(self) -> None:
        orig = Exception(
            "UNIQUE constraint failed: tenant_feature_grants.tenant_id, "
            "tenant_feature_grants.feature_key"
        )
        exc = IntegrityError("INSERT", {}, orig)
        self.assertTrue(_is_feature_grant_unique_violation(exc))

    def test_rejects_sqlite_message_for_different_table(self) -> None:
        orig = Exception("UNIQUE constraint failed: tenant_notification_rules.id")
        exc = IntegrityError("INSERT", {}, orig)
        self.assertFalse(_is_feature_grant_unique_violation(exc))

    def test_rejects_generic_unique_keyword_without_matching_columns(self) -> None:
        orig = Exception("UNIQUE constraint failed")
        exc = IntegrityError("INSERT", {}, orig)
        self.assertFalse(_is_feature_grant_unique_violation(exc))


if __name__ == "__main__":
    unittest.main()
