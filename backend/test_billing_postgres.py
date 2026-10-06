"""PostgreSQL-only Billing plan, usage and alert concurrency guarantees."""

from __future__ import annotations

import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import Barrier

BILLING_TEST_DATABASE_URL = os.environ.get("BILLING_TEST_DATABASE_URL")
if BILLING_TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = BILLING_TEST_DATABASE_URL

import app.models  # noqa: F401 - register every mapped table before create_all
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.modules.billing.infrastructure.models import TenantBillingPlan, TenantUsageAlert
from app.modules.billing.public import BillingFacade, BillingOnboardingFacade, BillingPlanInput
from app.modules.identity.infrastructure.models import Tenant
from app.models.analytics import Call

EXPECTED_DATABASE = "serviai_billing_test"
WORKERS = 6


def concurrently(workers: int, task):
    barrier = Barrier(workers)

    def run(index):
        barrier.wait(timeout=15)
        return task(index)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run, i) for i in range(workers)]
        return [future.result(timeout=60) for future in futures]


@unittest.skipUnless(BILLING_TEST_DATABASE_URL, "BILLING_TEST_DATABASE_URL not set")
class BillingPostgresConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = make_url(BILLING_TEST_DATABASE_URL)
        if url.get_backend_name() != "postgresql" or url.database != EXPECTED_DATABASE:
            raise RuntimeError(f"Billing tests require the dedicated PostgreSQL database {EXPECTED_DATABASE}")
        cls.engine = create_engine(
            BILLING_TEST_DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=10
        )
        Base.metadata.drop_all(cls.engine)
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def tenant_id(self):
        with self.Session() as db:
            tenant = Tenant(name="Billing test", slug=f"billing-{uuid.uuid4().hex}", timezone="UTC")
            db.add(tenant)
            db.commit()
            return tenant.id

    def add_plan(self, tenant_id: str, minutes: str = "2000", price: str = "0.14"):
        with self.Session() as db:
            BillingOnboardingFacade(db).create_default_plan(
                tenant_id, BillingPlanInput("enterprise", Decimal(minutes), Decimal(price))
            )
            db.commit()

    def add_call(self, tenant_id: str, minutes: str | None, *, started_at=None, status="answered"):
        with self.Session() as db:
            db.add(Call(
                tenant_id=tenant_id,
                external_provider="billing-test",
                external_call_id=uuid.uuid4().hex,
                normalized_status=status,
                started_at=started_at or datetime.now(UTC),
                billed_minutes=Decimal(minutes) if minutes is not None else None,
            ))
            db.commit()

    def count(self, model, *conditions) -> int:
        with self.Session() as db:
            return db.scalar(select(func.count()).select_from(model).where(*conditions))

    def test_concurrent_plan_creation_converges_to_one_row(self):
        tenant_id = self.tenant_id()

        def ensure(_index):
            with self.Session() as db:
                return BillingFacade(db).get_usage(tenant_id).plan

        plans = concurrently(WORKERS, ensure)
        self.assertEqual(len({plan.tenant_id for plan in plans}), 1)
        self.assertEqual(self.count(TenantBillingPlan, TenantBillingPlan.tenant_id == tenant_id), 1)

    def test_concurrent_usage_refresh_creates_three_alerts_once(self):
        tenant_id = self.tenant_id()
        self.add_plan(tenant_id)
        self.add_call(tenant_id, "2000")

        concurrently(WORKERS, lambda _i: self._usage_status(tenant_id))
        self.assertEqual(self.count(TenantUsageAlert, TenantUsageAlert.tenant_id == tenant_id), 3)
        with self.Session() as db:
            plan = db.scalar(select(TenantBillingPlan).where(TenantBillingPlan.tenant_id == tenant_id))
            tenant = db.get(Tenant, tenant_id)
            self.assertEqual(plan.usage_status, "suspended_usage_limit")
            self.assertEqual(tenant.status, "suspended_usage_limit")

    def _usage_status(self, tenant_id: str):
        with self.Session() as db:
            return BillingFacade(db).get_usage(tenant_id).usage_status

    def test_tenant_isolation_and_inclusive_billing_period(self):
        tenant_a, tenant_b = self.tenant_id(), self.tenant_id()
        self.add_plan(tenant_a)
        self.add_plan(tenant_b)
        start = datetime.now(UTC) - timedelta(days=1)
        end = datetime.now(UTC) + timedelta(days=1)
        with self.Session() as db:
            plan = db.scalar(select(TenantBillingPlan).where(TenantBillingPlan.tenant_id == tenant_a))
            plan.billing_period_start, plan.billing_period_end = start, end
            db.commit()
        self.add_call(tenant_a, "1", started_at=start - timedelta(seconds=1))
        self.add_call(tenant_a, "1", started_at=start)
        self.add_call(tenant_a, "1", started_at=end)
        self.add_call(tenant_a, "1", started_at=end + timedelta(seconds=1))
        self.add_call(tenant_a, "1", started_at=start, status="in_progress")
        self.add_call(tenant_a, None, started_at=start)
        self.add_call(tenant_b, "7")
        with self.Session() as db:
            usage_a = BillingFacade(db).get_usage(tenant_a).minutes_used
        with self.Session() as db:
            usage_b = BillingFacade(db).get_usage(tenant_b).minutes_used
        self.assertEqual(usage_a, Decimal("2.00"))
        self.assertEqual(usage_b, Decimal("7.00"))

    def test_concurrent_plan_updates_preserve_a_valid_plan(self):
        tenant_id = self.tenant_id()

        def update(index):
            plan = BillingPlanInput("enterprise", Decimal("3000" if index % 2 else "4000"), Decimal("0.14" if index % 2 else "0.15"))
            with self.Session() as db:
                return BillingFacade(db).update_plan(tenant_id, plan).plan

        concurrently(WORKERS, update)
        with self.Session() as db:
            plan = db.scalar(select(TenantBillingPlan).where(TenantBillingPlan.tenant_id == tenant_id))
            self.assertIn((plan.included_minutes, plan.price_per_minute_usd), {
                (Decimal("3000.00"), Decimal("0.1400")),
                (Decimal("4000.00"), Decimal("0.1500")),
            })
            self.assertEqual(self.count(TenantBillingPlan, TenantBillingPlan.tenant_id == tenant_id), 1)

    def test_usage_limit_suspension_recovers_after_plan_increase(self):
        tenant_id = self.tenant_id()
        self.add_plan(tenant_id)
        self.add_call(tenant_id, "2000")
        self._usage_status(tenant_id)
        with self.Session() as db:
            suspended = db.get(Tenant, tenant_id)
            self.assertEqual(suspended.status, "suspended_usage_limit")
            BillingFacade(db).update_plan(tenant_id, BillingPlanInput("enterprise", Decimal("3000"), Decimal("0.14")))
        with self.Session() as db:
            self.assertEqual(db.get(Tenant, tenant_id).status, "active")
            self.assertNotEqual(
                db.scalar(select(TenantBillingPlan.usage_status).where(TenantBillingPlan.tenant_id == tenant_id)),
                "suspended_usage_limit",
            )

    def test_repeated_usage_fetch_keeps_alert_rows_idempotent(self):
        tenant_id = self.tenant_id()
        self.add_plan(tenant_id)
        self.add_call(tenant_id, "2000")
        for _ in range(3):
            self._usage_status(tenant_id)
        self.assertEqual(self.count(TenantUsageAlert, TenantUsageAlert.tenant_id == tenant_id), 3)


if __name__ == "__main__":
    unittest.main()
