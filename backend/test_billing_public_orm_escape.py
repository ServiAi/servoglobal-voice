import unittest
from dataclasses import fields, is_dataclass
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401 - register mapped tables
from app.db.base import Base
from app.modules.billing.public import BillingAccessGate, BillingFacade, BillingOnboardingFacade, BillingPlanInput
from app.modules.identity.infrastructure.models import Tenant


class BillingPublicOrmEscapeTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.tenant = Tenant(name="Billing test", slug="billing-test", timezone="UTC")
        self.db.add(self.tenant)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def assert_public_value(self, value):
        self.assertNotIsInstance(value, Base)
        if is_dataclass(value):
            for field in fields(value):
                self.assert_public_value(getattr(value, field.name))
        elif isinstance(value, (list, tuple)):
            for item in value:
                self.assert_public_value(item)
        elif isinstance(value, dict):
            for item in value.values():
                self.assert_public_value(item)

    def test_facades_return_dtos_and_primitives_only(self):
        onboarding = BillingOnboardingFacade(self.db)
        onboarding.create_default_plan(self.tenant.id)
        self.db.commit()
        billing = BillingFacade(self.db)
        for value in (
            billing.get_usage(self.tenant.id),
            billing.get_savings_comparison(self.tenant.id),
            billing.update_plan(self.tenant.id, BillingPlanInput("enterprise", Decimal("2400"), Decimal("0.14"))),
            billing.list_usage_alerts(),
            billing.list_usage_summary(),
            onboarding.tenant_usage_snapshot(self.tenant.id),
            onboarding.cleanup_tenant(self.tenant.id),
            BillingAccessGate(self.db).ensure_call_allowed_by_slug(self.tenant.slug),
        ):
            self.assert_public_value(value)


if __name__ == "__main__":
    unittest.main()
