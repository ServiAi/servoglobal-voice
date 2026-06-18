from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
import unittest

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
TEST_DB_PATH = Path("serviai_tenant_usage_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.auth.deps import AuthContext, get_current_auth_context
from app.api.endpoints.admin.tenants import get_auth0_provisioning_service
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.analytics import Agent, Call
from app.models.billing import TenantBillingPlan, TenantUsageAlert
from app.models.identity import Tenant, TenantMembership, User
from app.schemas.billing import TenantPlanRequest
from app.services.auth0_provisioning_service import Auth0ProvisionedUser
from app.services.tenant_usage_service import TenantUsageService
from app.services.ultravox_ingestion_service import UltravoxIngestionService


class FakeAuth0ProvisioningService:
    def provision_tenant_admin(self, *, email: str, name: str) -> Auth0ProvisionedUser:
        return Auth0ProvisionedUser(
            user_id=f"auth0|{uuid.uuid4().hex}",
            email=email,
            name=name,
            connection="Username-Password-Authentication",
            verification_email_sent=True,
            password_reset_triggered=True,
        )

    def delete_user(self, user_id: str) -> None:
        return None


class TenantPlansUsageLimitsTests(unittest.TestCase):
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
        app.dependency_overrides[get_auth0_provisioning_service] = (
            lambda: FakeAuth0ProvisioningService()
        )
        app.dependency_overrides[get_current_auth_context] = self._auth_context_override

    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def _seed_internal_admin(self) -> User:
        with SessionLocal() as db:
            user = User(
                email="platform-admin@example.com",
                name="Platform Admin",
                is_internal=True,
                status="active",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            return user

    async def _auth_context_override(self) -> AuthContext:
        with SessionLocal() as db:
            tenant = db.scalar(select(Tenant).where(Tenant.slug == "system"))
            if tenant is None:
                tenant = Tenant(name="System", slug="system", timezone="UTC")
                db.add(tenant)
                db.commit()
                db.refresh(tenant)
            user = db.get(User, self.admin_user.id)
            assert user is not None
            return AuthContext(
                user=user,
                tenant=tenant,
                membership=TenantMembership(
                    tenant_id=tenant.id,
                    user_id=user.id,
                    role="platform_admin",
                    status="active",
                ),
            )

    def _tenant_payload(self, slug: str, plan: dict) -> dict:
        return {
            "name": f"Tenant {slug}",
            "slug": slug,
            "timezone": "America/Bogota",
            "status": "active",
            "plan": plan,
            "admin": {
                "name": "Tenant Admin",
                "email": f"{slug}@example.com",
                "role": "tenant_admin",
            },
            "agents": [],
        }

    def _seed_usage_tenant(
        self,
        *,
        slug: str = "usage-tenant",
        included_minutes: Decimal = Decimal("2000.00"),
        price: Decimal = Decimal("0.1400"),
    ) -> Tenant:
        with SessionLocal() as db:
            tenant = Tenant(name="Usage Tenant", slug=slug, timezone="UTC", status="active")
            db.add(tenant)
            db.flush()
            TenantUsageService(db).create_plan_for_tenant(
                tenant,
                TenantPlanRequest(
                    plan_key="enterprise",
                    included_minutes=included_minutes,
                    price_per_minute_usd=price,
                ),
            )
            db.commit()
            db.refresh(tenant)
            return tenant

    def _add_call(
        self,
        tenant_id: str,
        *,
        external_call_id: str,
        billed_minutes: Decimal | None,
        normalized_status: str = "answered",
    ) -> None:
        with SessionLocal() as db:
            db.add(
                Call(
                    tenant_id=tenant_id,
                    external_provider="ultravox",
                    external_call_id=external_call_id,
                    normalized_status=normalized_status,
                    started_at=datetime.now(UTC),
                    duration_seconds=120,
                    billed_minutes=billed_minutes,
                )
            )
            db.commit()

    def test_create_tenant_with_web_conversion_plan(self):
        response = self.client.post(
            "/api/v1/admin/tenants",
            json=self._tenant_payload(
                "web-plan",
                {"plan_key": "web_conversion"},
            ),
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["usage"]["plan"]["plan_key"], "web_conversion")
        self.assertEqual(payload["usage"]["plan"]["included_minutes"], 2000.0)
        self.assertEqual(payload["usage"]["plan"]["price_per_minute_usd"], 0.16)

    def test_create_tenant_with_voice_cloud_pbx_plan(self):
        response = self.client.post(
            "/api/v1/admin/tenants",
            json=self._tenant_payload(
                "voice-plan",
                {"plan_key": "voice_cloud_pbx"},
            ),
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["usage"]["plan"]["plan_key"], "voice_cloud_pbx")
        self.assertEqual(payload["usage"]["plan"]["price_per_minute_usd"], 0.18)

    def test_enterprise_plan_validates_minutes_and_price_range(self):
        accepted = self.client.post(
            "/api/v1/admin/tenants",
            json=self._tenant_payload(
                "enterprise-ok",
                {
                    "plan_key": "enterprise",
                    "included_minutes": 2500,
                    "price_per_minute_usd": 0.15,
                },
            ),
        )
        rejected = self.client.post(
            "/api/v1/admin/tenants",
            json=self._tenant_payload(
                "enterprise-bad",
                {
                    "plan_key": "enterprise",
                    "included_minutes": 2500,
                    "price_per_minute_usd": 0.16,
                },
            ),
        )

        self.assertEqual(accepted.status_code, 201)
        self.assertEqual(accepted.json()["usage"]["plan"]["included_minutes"], 2500.0)
        self.assertEqual(rejected.status_code, 422)

    def test_usage_calculates_from_billed_minutes_and_generates_deduplicated_alerts(self):
        tenant = self._seed_usage_tenant()
        self._add_call(tenant.id, external_call_id="bill-1", billed_minutes=Decimal("1600.00"))
        self._add_call(tenant.id, external_call_id="bill-2", billed_minutes=Decimal("300.00"))
        self._add_call(tenant.id, external_call_id="bill-3", billed_minutes=Decimal("100.00"))
        self._add_call(
            tenant.id,
            external_call_id="in-progress",
            billed_minutes=Decimal("500.00"),
            normalized_status="in_progress",
        )
        self._add_call(tenant.id, external_call_id="null-billing", billed_minutes=None)

        with SessionLocal() as db:
            tenant = db.get(Tenant, tenant.id)
            assert tenant is not None
            service = TenantUsageService(db)
            usage = service.get_usage(tenant)
            usage_again = service.get_usage(tenant)
            alert_count = db.scalar(select(func.count()).select_from(TenantUsageAlert))
            plan = db.scalar(
                select(TenantBillingPlan).where(TenantBillingPlan.tenant_id == tenant.id)
            )

        self.assertEqual(usage.minutes_used, 2000.0)
        self.assertEqual(usage.minutes_remaining, 0.0)
        self.assertEqual(usage.amount_spent_usd, 280.0)
        self.assertEqual(usage.usage_status, "suspended_usage_limit")
        self.assertEqual(len(usage.alerts), 3)
        self.assertEqual(len(usage_again.alerts), 3)
        self.assertEqual(alert_count, 3)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.usage_status, "suspended_usage_limit")

    def test_savings_comparison_uses_configured_provider_prices(self):
        tenant = self._seed_usage_tenant(slug="savings-tenant")
        self._add_call(tenant.id, external_call_id="bill-1", billed_minutes=Decimal("100.00"))

        with SessionLocal() as db:
            tenant = db.get(Tenant, tenant.id)
            assert tenant is not None
            comparison = TenantUsageService(db).get_savings_comparison(tenant)

        providers = {provider.provider_key: provider for provider in comparison.providers}
        self.assertEqual(comparison.serviglobal_cost_usd, 14.0)
        self.assertEqual(providers["vapi"].provider_price_per_minute_usd, 0.05)
        self.assertEqual(providers["retell"].provider_price_per_minute_usd, 0.11)
        self.assertEqual(providers["custom"].provider_price_per_minute_usd, None)

    def test_exhausted_tenant_blocks_new_calls_but_admin_can_still_view_it(self):
        tenant = self._seed_usage_tenant(slug="blocked-tenant")
        self._add_call(tenant.id, external_call_id="bill-1", billed_minutes=Decimal("2000.00"))

        with SessionLocal() as db:
            tenant = db.get(Tenant, tenant.id)
            assert tenant is not None
            service = TenantUsageService(db)
            service.get_usage(tenant)
            with self.assertRaises(HTTPException) as exc:
                service.ensure_tenant_can_start_call_by_slug("blocked-tenant")

        response = self.client.get("/api/v1/admin/tenants")
        self.assertEqual(exc.exception.status_code, 402)
        self.assertEqual(exc.exception.detail, "Tenant minute package exhausted")
        self.assertEqual(response.status_code, 200)
        listed = [item for item in response.json() if item["slug"] == "blocked-tenant"]
        self.assertEqual(listed[0]["usage"]["usage_status"], "suspended_usage_limit")

    def test_late_ultravox_webhook_can_update_exhausted_tenant(self):
        tenant = self._seed_usage_tenant(slug="late-webhook")
        self._add_call(tenant.id, external_call_id="bill-1", billed_minutes=Decimal("2000.00"))

        with SessionLocal() as db:
            tenant = db.get(Tenant, tenant.id)
            assert tenant is not None
            db.add(
                Agent(
                    tenant_id=tenant.id,
                    name="Late Agent",
                    external_provider="ultravox",
                    external_agent_id="agent-late",
                )
            )
            TenantUsageService(db).get_usage(tenant)
            result = UltravoxIngestionService(db).ingest_event(
                {
                    "eventType": "call.billed",
                    "callId": "late-call",
                    "created": "2026-05-30T12:00:00Z",
                    "ended": "2026-05-30T12:02:00Z",
                    "billedMinutes": 2,
                    "call": {"agent": {"agentId": "agent-late"}},
                    "metadata": {"tenant_slug": "late-webhook"},
                }
            )

        self.assertEqual(result.call.external_call_id, "late-call")
        self.assertEqual(result.call.billed_minutes, Decimal("2"))


if __name__ == "__main__":
    unittest.main()
