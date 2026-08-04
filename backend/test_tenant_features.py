from __future__ import annotations

import os
from pathlib import Path
import unittest

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")
os.environ["SERVIAI_TEST_SECRET_FALLBACK"] = "1"
TEST_DB_PATH = Path("serviai_tenant_features_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.auth.deps import AuthContext, get_current_auth_context
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.identity import Tenant, TenantMembership, User
from app.models.tenant_features import TenantFeatureGrant
from app.services.tenant_feature_service import (
    TenantFeatureService,
    TenantFeatureDisabledError,
    UnknownTenantFeatureError,
    VOICE_EXPERIENCES,
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
        self.tenant_a_id, self.tenant_b_id, self.platform_user_id, self.tenant_user_id = (
            self._seed_data()
        )
        self.current_user_id = self.platform_user_id
        app.dependency_overrides[get_current_auth_context] = self._auth_context_override
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def _seed_data(self) -> tuple[str, str, str, str]:
        with SessionLocal() as db:
            tenant_a = Tenant(name="Tenant A", slug="tenant-a")
            tenant_b = Tenant(name="Tenant B", slug="tenant-b")
            platform_user = User(
                email="platform@example.com",
                name="Platform Admin",
                status="active",
                is_internal=False,
            )
            tenant_user = User(
                email="tenant@example.com",
                name="Tenant Admin",
                status="active",
                is_internal=False,
            )
            db.add_all([tenant_a, tenant_b, platform_user, tenant_user])
            db.flush()
            db.add_all(
                [
                    TenantMembership(
                        tenant_id=tenant_a.id,
                        user_id=platform_user.id,
                        role="platform_admin",
                        status="active",
                    ),
                    TenantMembership(
                        tenant_id=tenant_a.id,
                        user_id=tenant_user.id,
                        role="tenant_admin",
                        status="active",
                    ),
                ]
            )
            db.commit()
            return tenant_a.id, tenant_b.id, platform_user.id, tenant_user.id

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

    def _put(self, tenant_id: str, payload: dict | None = None):
        return self.client.put(
            f"/api/v1/admin/tenants/{tenant_id}/features/voice-experiences",
            json=payload or self._payload(),
        )

    def test_platform_admin_can_create_enabled_feature(self) -> None:
        response = self._put(self.tenant_a_id)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["enabled"])
        with SessionLocal() as db:
            grant = db.scalar(
                select(TenantFeatureGrant).where(
                    TenantFeatureGrant.tenant_id == self.tenant_a_id
                )
            )
            self.assertEqual(grant.feature_key, VOICE_EXPERIENCES)
            self.assertTrue(grant.enabled)
            self.assertEqual(grant.enabled_by_user_id, self.platform_user_id)

    def test_internal_platform_user_can_configure_feature(self) -> None:
        with SessionLocal() as db:
            user = db.get(User, self.platform_user_id)
            membership = db.scalar(
                select(TenantMembership).where(
                    TenantMembership.user_id == self.platform_user_id
                )
            )
            user.is_internal = True
            membership.role = "tenant_admin"
            db.commit()

        self.assertEqual(self._put(self.tenant_a_id).status_code, 200)

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

    def test_concurrent_create_retries_the_unique_constraint_winner(self) -> None:
        with SessionLocal() as db:
            original_commit = db.commit
            original_rollback = db.rollback
            first_commit = True

            def commit_with_race() -> None:
                nonlocal first_commit
                if first_commit:
                    first_commit = False
                    raise IntegrityError("insert tenant feature", {}, Exception("unique"))
                original_commit()

            def rollback_with_concurrent_winner() -> None:
                original_rollback()
                with SessionLocal() as concurrent_db:
                    concurrent_db.add(
                        TenantFeatureGrant(
                            tenant_id=self.tenant_a_id,
                            feature_key=VOICE_EXPERIENCES,
                            enabled=False,
                            limits_json={
                                "max_experiences": 1,
                                "max_context_fields": 1,
                            },
                            enabled_by_user_id=self.platform_user_id,
                        )
                    )
                    concurrent_db.commit()

            db.commit = commit_with_race
            db.rollback = rollback_with_concurrent_winner
            grant = TenantFeatureService(db).set_feature(
                self.tenant_a_id,
                VOICE_EXPERIENCES,
                True,
                self._payload()["limits"],
                self.platform_user_id,
            )

            self.assertTrue(grant.enabled)
            self.assertEqual(grant.limits_json, self._payload()["limits"])

        with SessionLocal() as db:
            count = db.scalar(select(func.count()).select_from(TenantFeatureGrant))
            self.assertEqual(count, 1)

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
                    self.platform_user_id,
                )

    def test_unknown_tenant_is_rejected(self) -> None:
        with SessionLocal() as db:
            db.get(User, self.platform_user_id).is_internal = True
            db.commit()

        list_response = self.client.get(
            "/api/v1/admin/tenants/missing-tenant/features"
        )
        put_response = self._put("missing-tenant")

        self.assertEqual(list_response.status_code, 404)
        self.assertEqual(put_response.status_code, 404)

    def test_features_are_isolated_between_tenants(self) -> None:
        with SessionLocal() as db:
            db.get(User, self.platform_user_id).is_internal = True
            db.commit()

        self.assertEqual(self._put(self.tenant_a_id).status_code, 200)
        self.assertEqual(self._put(self.tenant_b_id, self._payload(False)).status_code, 200)

        tenant_a = self.client.get(
            f"/api/v1/admin/tenants/{self.tenant_a_id}/features"
        ).json()
        tenant_b = self.client.get(
            f"/api/v1/admin/tenants/{self.tenant_b_id}/features"
        ).json()
        self.assertTrue(tenant_a[0]["enabled"])
        self.assertFalse(tenant_b[0]["enabled"])

    def test_non_internal_platform_admin_cannot_access_another_tenant(self) -> None:
        get_response = self.client.get(
            f"/api/v1/admin/tenants/{self.tenant_b_id}/features"
        )
        put_response = self._put(self.tenant_b_id)

        self.assertEqual(get_response.status_code, 403)
        self.assertEqual(put_response.status_code, 403)

    def test_tenant_user_cannot_use_admin_feature_endpoints(self) -> None:
        self.current_user_id = self.tenant_user_id

        self.assertEqual(
            self.client.get(
                f"/api/v1/admin/tenants/{self.tenant_a_id}/features"
            ).status_code,
            403,
        )
        self.assertEqual(self._put(self.tenant_a_id).status_code, 403)

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
        self.assertNotIn(self.platform_user_id, response.text)
        self.assertNotIn("platform@example.com", response.text)


if __name__ == "__main__":
    unittest.main()
