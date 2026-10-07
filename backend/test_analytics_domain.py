"""Pure Analytics domain rules: no database, no framework."""

from __future__ import annotations

import unittest
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.modules.analytics.domain.dashboard import (
    decimal_sum,
    local_datetime,
    nullable_decimal_to_float,
    parse_filter_datetime,
    percentage,
    resolve_filters,
    tenant_timezone,
    validate_page,
)
from app.modules.analytics.domain.errors import InvalidDashboardFilterError
from app.modules.analytics.domain.statuses import (
    NORMALIZED_CALL_STATUSES,
    TERMINAL_CALL_STATUSES,
    CallStatusNormalizer,
    is_status_regression,
)

BOGOTA = ZoneInfo("America/Bogota")


class StatusNormalizationTests(unittest.TestCase):
    def test_vocabulary_is_preserved(self):
        self.assertEqual(
            NORMALIZED_CALL_STATUSES,
            ("in_progress", "answered", "unanswered", "rejected", "failed", "cancelled", "transferred", "voicemail"),
        )
        self.assertEqual(TERMINAL_CALL_STATUSES, set(NORMALIZED_CALL_STATUSES) - {"in_progress"})

    def test_provider_statuses_map_to_the_normalized_vocabulary(self):
        normalizer = CallStatusNormalizer()
        cases = {
            "ringing": "in_progress",
            " Completed ": "answered",
            "missed": "unanswered",
            "declined": "rejected",
            "failure": "failed",
            "canceled": "cancelled",
            "human_transfer": "transferred",
            "voicemail": "voicemail",
            "call.billed": "answered",
            "BILLING_STATUS_FREE_SYSTEM_ERROR": "failed",
        }
        for provider_status, expected in cases.items():
            with self.subTest(provider_status=provider_status):
                self.assertEqual(normalizer.normalize(provider_status), expected)

    def test_unknown_status_uses_the_fallback_and_an_invalid_fallback_fails_the_call(self):
        normalizer = CallStatusNormalizer()
        self.assertEqual(normalizer.normalize("something-new"), "in_progress")
        self.assertEqual(normalizer.normalize(None, fallback="answered"), "answered")
        self.assertEqual(normalizer.normalize("something-new", fallback="bogus"), "failed")

    def test_a_late_partial_update_never_reopens_a_finished_call(self):
        for terminal in TERMINAL_CALL_STATUSES:
            with self.subTest(status=terminal):
                self.assertTrue(is_status_regression(terminal, "in_progress", partial_update=True))
        self.assertFalse(is_status_regression("in_progress", "in_progress", partial_update=True))
        self.assertFalse(is_status_regression("answered", "in_progress", partial_update=False))
        self.assertFalse(is_status_regression("answered", "failed", partial_update=True))
        self.assertFalse(is_status_regression("answered", None, partial_update=True))


class FilterValidationTests(unittest.TestCase):
    def _resolve(self, **kwargs):
        values = {"from_value": None, "to_value": None, "agent_id": None, "status": None, "timezone": BOGOTA}
        values.update(kwargs)
        return resolve_filters(**values)

    def test_unknown_status_is_rejected_with_the_allowed_list(self):
        with self.assertRaises(InvalidDashboardFilterError) as ctx:
            self._resolve(status="nope")
        self.assertIn("status must be one of: in_progress, answered", str(ctx.exception))

    def test_range_must_be_ordered_and_parsable(self):
        with self.assertRaisesRegex(InvalidDashboardFilterError, "earlier than or equal"):
            self._resolve(from_value="2026-05-03", to_value="2026-05-02")
        with self.assertRaisesRegex(InvalidDashboardFilterError, "ISO dates or datetimes"):
            self._resolve(from_value="yesterday")
        self.assertIsNone(self._resolve(from_value="", to_value=None).from_datetime)

    def test_date_only_values_span_the_whole_local_day(self):
        resolved = self._resolve(from_value="2026-05-02", to_value="2026-05-02", agent_id="a1", status="answered")
        self.assertEqual(resolved.from_datetime, datetime(2026, 5, 2, 0, 0, tzinfo=BOGOTA))
        self.assertEqual(resolved.to_datetime, datetime(2026, 5, 2, 23, 59, 59, 999999, tzinfo=BOGOTA))
        self.assertEqual((resolved.agent_id, resolved.status), ("a1", "answered"))

    def test_naive_datetimes_take_the_tenant_zone_and_z_means_utc(self):
        self.assertEqual(
            parse_filter_datetime("2026-05-02T10:00:00", BOGOTA, is_end=False), datetime(2026, 5, 2, 10, tzinfo=BOGOTA)
        )
        self.assertEqual(
            parse_filter_datetime("2026-05-02T10:00:00Z", BOGOTA, is_end=False), datetime(2026, 5, 2, 10, tzinfo=UTC)
        )

    def test_pagination_bounds(self):
        validate_page(1, 1)
        validate_page(3, 100)
        for page, page_size, message in ((0, 20, "page must be"), (1, 0, "page_size must be"), (1, 101, "page_size must be")):
            with self.subTest(page=page, page_size=page_size), self.assertRaisesRegex(InvalidDashboardFilterError, message):
                validate_page(page, page_size)


class CalculationTests(unittest.TestCase):
    def test_percentages_round_and_guard_zero(self):
        self.assertEqual(percentage(1, 3), 33.33)
        self.assertEqual(percentage(2, 3), 66.67)
        self.assertEqual(percentage(5, 0), 0.0)
        self.assertEqual(percentage(0, 4), 0.0)

    def test_decimal_helpers(self):
        self.assertEqual(decimal_sum([Decimal("1.50"), None, Decimal("2.10")]), 3.6)
        self.assertIsNone(nullable_decimal_to_float(None))
        self.assertEqual(nullable_decimal_to_float(Decimal("2.50")), 2.5)

    def test_timezone_conversion_and_unknown_zone_fallback(self):
        self.assertEqual(tenant_timezone("America/Bogota"), BOGOTA)
        self.assertEqual(tenant_timezone("Not/AZone"), ZoneInfo("UTC"))
        self.assertEqual(tenant_timezone(None), ZoneInfo("UTC"))
        late_utc = datetime(2026, 5, 3, 3, 30, tzinfo=UTC)
        self.assertEqual(local_datetime(late_utc, BOGOTA).date(), date(2026, 5, 2))
        self.assertEqual(local_datetime(datetime(2026, 5, 2, 23, 0), BOGOTA).date(), date(2026, 5, 2))


if __name__ == "__main__":
    unittest.main()
