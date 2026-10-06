import unittest
from decimal import Decimal

from app.modules.billing.domain.errors import InvalidBillingPlanError
from app.modules.billing.domain.plans import (
    PLAN_ENTERPRISE,
    PLAN_VOICE_CLOUD_PBX,
    PLAN_WEB_CONVERSION,
    normalize_plan,
)
from app.modules.billing.domain.pricing import savings
from app.modules.billing.domain.usage import reached_alert_thresholds, status_for_usage


class BillingDomainTests(unittest.TestCase):
    def test_plan_defaults_and_enterprise_validation(self):
        self.assertEqual(
            normalize_plan(PLAN_WEB_CONVERSION),
            ("Plan Web Conversion", Decimal("2000.00"), Decimal("0.1600")),
        )
        self.assertEqual(
            normalize_plan(PLAN_VOICE_CLOUD_PBX),
            ("Plan Voice Cloud / PBX", Decimal("2000.00"), Decimal("0.1800")),
        )
        self.assertEqual(
            normalize_plan(PLAN_ENTERPRISE, Decimal("2000.009"), Decimal("0.14555")),
            ("Enterprise", Decimal("2000.01"), Decimal("0.1456")),
        )
        with self.assertRaises(InvalidBillingPlanError):
            normalize_plan(PLAN_ENTERPRISE, Decimal("1999.99"), Decimal("0.15"))
        with self.assertRaises(InvalidBillingPlanError):
            normalize_plan(PLAN_ENTERPRISE, Decimal("2000"), Decimal("0.1501"))

    def test_usage_and_alert_boundaries(self):
        cases = (
            ("0", "normal", ()),
            ("79.99", "normal", ()),
            ("80", "approaching_limit", (80,)),
            ("89.99", "approaching_limit", (80,)),
            ("90", "approaching_limit", (80, 90)),
            ("99.99", "approaching_limit", (80, 90)),
            ("100", "limit_reached", (80, 90, 100)),
            ("100.01", "over_limit", (80, 90, 100)),
        )
        for value, expected_status, expected_thresholds in cases:
            usage = Decimal(value)
            self.assertEqual(status_for_usage(usage), expected_status)
            self.assertEqual(reached_alert_thresholds(usage), expected_thresholds)

    def test_decimal_cost_and_savings_keep_precision(self):
        provider_cost, own_cost, amount, percent = savings(
            Decimal("12.50"), Decimal("0.20"), Decimal("0.16")
        )
        self.assertEqual((provider_cost, own_cost, amount), (Decimal("2.5000"), Decimal("2.0000"), Decimal("0.5000")))
        self.assertEqual(percent, Decimal("20.000"))
        self.assertEqual(savings(Decimal("2"), None, Decimal("0.16")), (None, Decimal("0.32"), None, None))


if __name__ == "__main__":
    unittest.main()
