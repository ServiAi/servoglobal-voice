from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.domain.notification_event_schemas import (
    NotificationEventSchemaError,
    get_notification_event_schema,
    validate_rule_event_schema,
)
from app.domain.notification_rules import NotificationCondition, NotificationConditionOperator
from app.services.notification_condition_service import NotificationConditionService


class NotificationEventSchemaTests(unittest.TestCase):
    def test_booking_schema_matches_real_payload_contract(self):
        schema = get_notification_event_schema("booking_notifications", "booking.created")
        self.assertIsNotNone(schema)
        self.assertEqual(schema.version, 1)
        self.assertEqual(schema.field("booking.start_at").data_type, "datetime")
        self.assertTrue(schema.field("customer.phone").recipient_eligible)

    def test_schema_rejects_operator_incompatible_with_field_type(self):
        rule = SimpleNamespace(
            capability_key="booking_notifications",
            event_type="booking.created",
            conditions_mode="all",
            variable_mapping_json={},
            recipient_strategy="event_customer",
            recipient_group_key=None,
        )
        condition = NotificationCondition(
            field="booking.start_at",
            operator=NotificationConditionOperator.CONTAINS,
            value="2026",
        )
        with self.assertRaisesRegex(NotificationEventSchemaError, "condition_operator_not_allowed_for_field"):
            validate_rule_event_schema(rule, [condition])

    def test_condition_service_supports_all_and_any(self):
        conditions = [
            NotificationCondition(field="booking.status", operator="equals", value="scheduled"),
            NotificationCondition(field="booking.title", operator="contains", value="Venta"),
        ]
        payload = {"booking": {"status": "scheduled", "title": "Consulta inicial"}}
        service = NotificationConditionService()
        self.assertFalse(service.matches(conditions=conditions, payload=payload, mode="all"))
        self.assertTrue(service.matches(conditions=conditions, payload=payload, mode="any"))

    def test_datetime_condition_requires_timezone_aware_iso_value(self):
        rule = SimpleNamespace(
            capability_key="booking_notifications",
            event_type="booking.created",
            conditions_mode="all",
            variable_mapping_json={},
            recipient_strategy="event_customer",
            recipient_group_key=None,
        )
        condition = NotificationCondition(
            field="booking.start_at",
            operator=NotificationConditionOperator.GREATER_THAN,
            value="2026-08-12T15:00:00",
        )
        with self.assertRaisesRegex(NotificationEventSchemaError, "condition_value_invalid_for_field"):
            validate_rule_event_schema(rule, [condition])

    def test_empty_condition_list_matches_in_both_modes(self):
        service = NotificationConditionService()
        self.assertTrue(service.matches(conditions=[], payload={}, mode="all"))
        self.assertTrue(service.matches(conditions=[], payload={}, mode="any"))


if __name__ == "__main__":
    unittest.main()
