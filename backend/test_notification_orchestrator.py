import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import event as sa_event

TEST_DB_PATH = Path("serviai_notification_orchestrator_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.domain.notification_rules import (
    NotificationCondition,
    NotificationConditionEvaluationError,
    NotificationConditionOperator,
    NotificationEventProcessingError,
    NotificationRecipientResolutionError,
    NotificationRuleConfigurationError,
)
from app.models.crm import CrmWhatsAppMessage
from app.models.identity import Tenant
from app.models.notifications import (
    DomainEvent,
    NotificationDelivery,
    TenantCapability,
    TenantNotificationRecipient,
    TenantNotificationRule,
)
from app.services.domain_event_service import DomainEventService
from app.services.notification_capability_service import NotificationCapabilityService
from app.services.notification_condition_service import NotificationConditionService
from app.services.notification_orchestrator import NotificationOrchestrator
from app.services.notification_recipient_service import NotificationRecipientService
from app.services.notification_rule_service import NotificationRuleService


@sa_event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


FIXED_NOW = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
PAST_AVAILABLE_AT = datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc)
FUTURE_AVAILABLE_AT = datetime(2026, 8, 5, 0, 0, 0, tzinfo=timezone.utc)

_PHASE3_SOURCE_FILES = [
    Path("app/domain/notification_rules.py"),
    Path("app/services/notification_capability_service.py"),
    Path("app/services/notification_rule_service.py"),
    Path("app/services/notification_condition_service.py"),
    Path("app/services/notification_recipient_service.py"),
    Path("app/services/notification_orchestrator.py"),
]


def _naive(value: datetime) -> datetime:
    # SQLite no conserva tzinfo en columnas DateTime(timezone=True) tras un
    # refresh; comparamos en hora "naive" asumiendo siempre convencion UTC.
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def _valid_booking_payload(**overrides) -> dict:
    payload = {
        "booking": {
            "id": "bk-1",
            "status": "confirmed",
            "start_at": "2026-08-01T15:00:00+00:00",
            "timezone": "America/Bogota",
        },
        "customer": {"phone": "+573001112233"},
        "lead": {"id": "lead-1", "status": "qualified"},
        "custom": {"property_id": "prop-1"},
    }
    payload.update(overrides)
    return payload


class _BaseNotificationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TEST_DB_PATH.unlink(missing_ok=True)
        Base.metadata.create_all(bind=engine)

    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        TEST_DB_PATH.unlink(missing_ok=True)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def _create_tenant(self, slug: str) -> str:
        tenant = Tenant(name=f"Empresa {slug}", slug=slug)
        self.db.add(tenant)
        self.db.commit()
        self.db.refresh(tenant)
        return tenant.id

    def _create_capability(
        self, *, tenant_id: str, capability_key: str = "booking_notifications", enabled: bool = True
    ) -> TenantCapability:
        capability = TenantCapability(tenant_id=tenant_id, capability_key=capability_key, enabled=enabled)
        self.db.add(capability)
        self.db.commit()
        self.db.refresh(capability)
        return capability

    def _enable_capability(self, tenant_id: str, capability_key: str = "booking_notifications") -> None:
        self._create_capability(tenant_id=tenant_id, capability_key=capability_key, enabled=True)

    def _create_rule(self, *, tenant_id: str, **overrides) -> TenantNotificationRule:
        defaults = dict(
            tenant_id=tenant_id,
            name="Regla de prueba",
            capability_key="booking_notifications",
            event_type="booking.created",
            channel="whatsapp",
            action_type="send_whatsapp_template",
            template_key="tpl_booking_confirmed",
            recipient_strategy="event_customer",
            recipient_group_key=None,
            conditions_json=[],
            variable_mapping_json={},
            schedule_mode="immediate",
            schedule_offset_minutes=0,
            priority=100,
            enabled=True,
        )
        defaults.update(overrides)
        rule = TenantNotificationRule(**defaults)
        self.db.add(rule)
        self.db.commit()
        self.db.refresh(rule)
        return rule

    def _create_recipient(
        self,
        *,
        tenant_id: str,
        group_key: str,
        destination: str,
        channel: str = "whatsapp",
        status: str = "active",
    ) -> TenantNotificationRecipient:
        recipient = TenantNotificationRecipient(
            tenant_id=tenant_id,
            group_key=group_key,
            name="Destinatario de prueba",
            channel=channel,
            destination=destination,
            status=status,
        )
        self.db.add(recipient)
        self.db.commit()
        self.db.refresh(recipient)
        return recipient

    def _publish_event(
        self,
        *,
        tenant_id: str,
        idempotency_key: str,
        payload: dict,
        event_type: str = "booking.created",
        source: str = "calcom",
        available_at: datetime | None = None,
    ) -> DomainEvent:
        return DomainEventService(self.db).publish(
            tenant_id=tenant_id,
            event_type=event_type,
            source=source,
            idempotency_key=idempotency_key,
            payload=payload,
            available_at=available_at or PAST_AVAILABLE_AT,
        ).event


# ---------------------------------------------------------------------------
# Capacidades — 1 a 4
# ---------------------------------------------------------------------------
class NotificationCapabilityServiceTests(_BaseNotificationTestCase):
    def test_enabled_capability_returns_true(self):
        tenant_id = self._create_tenant("cap-enabled")
        self._create_capability(tenant_id=tenant_id, enabled=True)
        service = NotificationCapabilityService(self.db)
        self.assertTrue(service.is_enabled(tenant_id=tenant_id, capability_key="booking_notifications"))

    def test_disabled_capability_returns_false(self):
        tenant_id = self._create_tenant("cap-disabled")
        self._create_capability(tenant_id=tenant_id, enabled=False)
        service = NotificationCapabilityService(self.db)
        self.assertFalse(service.is_enabled(tenant_id=tenant_id, capability_key="booking_notifications"))

    def test_missing_capability_returns_false(self):
        tenant_id = self._create_tenant("cap-missing")
        service = NotificationCapabilityService(self.db)
        self.assertFalse(service.is_enabled(tenant_id=tenant_id, capability_key="booking_notifications"))

    def test_capability_from_other_tenant_does_not_apply(self):
        tenant_a = self._create_tenant("cap-tenant-a")
        tenant_b = self._create_tenant("cap-tenant-b")
        self._create_capability(tenant_id=tenant_a, enabled=True)
        service = NotificationCapabilityService(self.db)
        self.assertFalse(service.is_enabled(tenant_id=tenant_b, capability_key="booking_notifications"))


# ---------------------------------------------------------------------------
# Reglas — 5 a 8
# ---------------------------------------------------------------------------
class NotificationRuleServiceTests(_BaseNotificationTestCase):
    def test_only_active_rules_returned(self):
        tenant_id = self._create_tenant("rules-active")
        self._create_rule(tenant_id=tenant_id, name="activa", enabled=True)
        self._create_rule(tenant_id=tenant_id, name="inactiva", enabled=False)
        service = NotificationRuleService(self.db)
        rules = service.get_active_rules(tenant_id=tenant_id, event_type="booking.created")
        self.assertEqual([rule.name for rule in rules], ["activa"])

    def test_only_rules_for_tenant(self):
        tenant_a = self._create_tenant("rules-tenant-a")
        tenant_b = self._create_tenant("rules-tenant-b")
        self._create_rule(tenant_id=tenant_a, name="regla-a")
        self._create_rule(tenant_id=tenant_b, name="regla-b")
        service = NotificationRuleService(self.db)
        rules = service.get_active_rules(tenant_id=tenant_a, event_type="booking.created")
        self.assertEqual([rule.name for rule in rules], ["regla-a"])

    def test_only_rules_for_event_type(self):
        tenant_id = self._create_tenant("rules-event-type")
        self._create_rule(tenant_id=tenant_id, name="booking-rule", event_type="booking.created")
        self._create_rule(tenant_id=tenant_id, name="call-rule", event_type="call.completed")
        service = NotificationRuleService(self.db)
        rules = service.get_active_rules(tenant_id=tenant_id, event_type="booking.created")
        self.assertEqual([rule.name for rule in rules], ["booking-rule"])

    def test_rules_ordered_by_priority(self):
        tenant_id = self._create_tenant("rules-priority")
        self._create_rule(tenant_id=tenant_id, name="low", priority=200)
        self._create_rule(tenant_id=tenant_id, name="high", priority=10)
        self._create_rule(tenant_id=tenant_id, name="mid", priority=100)
        service = NotificationRuleService(self.db)
        rules = service.get_active_rules(tenant_id=tenant_id, event_type="booking.created")
        self.assertEqual([rule.name for rule in rules], ["high", "mid", "low"])


# ---------------------------------------------------------------------------
# Condiciones — 9 a 25
# ---------------------------------------------------------------------------
class NotificationConditionServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = NotificationConditionService()
        self.payload = {
            "booking": {"status": "confirmed", "duration_minutes": 30},
            "customer": {"phone": "+573001112233"},
            "lead": {"status": "qualified"},
            "custom": {"score": 42, "tags": ["vip"], "notes": ""},
        }

    @staticmethod
    def _cond(field, operator, value=None):
        return NotificationCondition(field=field, operator=operator, value=value)

    def test_equals(self):
        cond = self._cond("booking.status", NotificationConditionOperator.EQUALS, "confirmed")
        self.assertTrue(self.service.matches(conditions=[cond], payload=self.payload))

    def test_not_equals(self):
        cond = self._cond("booking.status", NotificationConditionOperator.NOT_EQUALS, "cancelled")
        self.assertTrue(self.service.matches(conditions=[cond], payload=self.payload))

    def test_in(self):
        cond = self._cond("booking.status", NotificationConditionOperator.IN, ["confirmed", "pending"])
        self.assertTrue(self.service.matches(conditions=[cond], payload=self.payload))

    def test_not_in(self):
        cond = self._cond("booking.status", NotificationConditionOperator.NOT_IN, ["cancelled"])
        self.assertTrue(self.service.matches(conditions=[cond], payload=self.payload))

    def test_exists(self):
        cond = self._cond("customer.phone", NotificationConditionOperator.EXISTS)
        self.assertTrue(self.service.matches(conditions=[cond], payload=self.payload))

    def test_not_exists(self):
        cond = self._cond("custom.missing_field", NotificationConditionOperator.NOT_EXISTS)
        self.assertTrue(self.service.matches(conditions=[cond], payload=self.payload))

    def test_not_empty(self):
        present = self._cond("custom.tags", NotificationConditionOperator.NOT_EMPTY)
        self.assertTrue(self.service.matches(conditions=[present], payload=self.payload))
        empty = self._cond("custom.notes", NotificationConditionOperator.NOT_EMPTY)
        self.assertFalse(self.service.matches(conditions=[empty], payload=self.payload))

    def test_greater_than(self):
        cond = self._cond("custom.score", NotificationConditionOperator.GREATER_THAN, 10)
        self.assertTrue(self.service.matches(conditions=[cond], payload=self.payload))

    def test_greater_than_or_equal(self):
        cond = self._cond("custom.score", NotificationConditionOperator.GREATER_THAN_OR_EQUAL, 42)
        self.assertTrue(self.service.matches(conditions=[cond], payload=self.payload))

    def test_less_than(self):
        cond = self._cond("custom.score", NotificationConditionOperator.LESS_THAN, 100)
        self.assertTrue(self.service.matches(conditions=[cond], payload=self.payload))

    def test_less_than_or_equal(self):
        cond = self._cond("custom.score", NotificationConditionOperator.LESS_THAN_OR_EQUAL, 42)
        self.assertTrue(self.service.matches(conditions=[cond], payload=self.payload))

    def test_numeric_comparison_rejects_bool(self):
        cond = self._cond("custom.flag", NotificationConditionOperator.GREATER_THAN, 1)
        payload = {"custom": {"flag": True}}
        with self.assertRaises(NotificationConditionEvaluationError):
            self.service.matches(conditions=[cond], payload=payload)

    def test_missing_path_returns_false_for_equals(self):
        cond = self._cond("custom.missing", NotificationConditionOperator.EQUALS, "x")
        self.assertFalse(self.service.matches(conditions=[cond], payload=self.payload))

    def test_multiple_conditions_use_and(self):
        status_ok = self._cond("booking.status", NotificationConditionOperator.EQUALS, "confirmed")
        score_too_high = self._cond("custom.score", NotificationConditionOperator.GREATER_THAN, 100)
        self.assertFalse(self.service.matches(conditions=[status_ok, score_too_high], payload=self.payload))
        score_ok = self._cond("custom.score", NotificationConditionOperator.GREATER_THAN, 10)
        self.assertTrue(self.service.matches(conditions=[status_ok, score_ok], payload=self.payload))

    def test_malformed_condition_is_rejected(self):
        with self.assertRaises(PydanticValidationError):
            NotificationCondition(
                field="custom.score", operator=NotificationConditionOperator.IN, value="not-a-list"
            )

    def test_dangerous_path_is_rejected(self):
        with self.assertRaises(PydanticValidationError):
            NotificationCondition(field="custom.__class__", operator=NotificationConditionOperator.EXISTS)

    def test_no_eval_or_getattr_used(self):
        for path in _PHASE3_SOURCE_FILES:
            content = path.read_text(encoding="utf-8")
            self.assertNotIn("eval(", content)
            self.assertNotIn("getattr(", content)


# ---------------------------------------------------------------------------
# Destinatarios — 26 a 34
# ---------------------------------------------------------------------------
class NotificationRecipientServiceTests(_BaseNotificationTestCase):
    def test_event_customer_resolves_phone(self):
        tenant_id = self._create_tenant("recipient-customer")
        rule = self._create_rule(tenant_id=tenant_id, recipient_strategy="event_customer")
        service = NotificationRecipientService(self.db)
        result = service.resolve(
            tenant_id=tenant_id, rule=rule, payload={"customer": {"phone": "+573001112233"}}
        )
        self.assertEqual(result, ["+573001112233"])

    def test_customer_without_phone_returns_empty_list(self):
        tenant_id = self._create_tenant("recipient-no-phone")
        rule = self._create_rule(tenant_id=tenant_id, recipient_strategy="event_customer")
        service = NotificationRecipientService(self.db)
        result = service.resolve(
            tenant_id=tenant_id, rule=rule, payload={"customer": {"email": "demo@example.com"}}
        )
        self.assertEqual(result, [])

    def test_configured_group_returns_multiple_destinations(self):
        tenant_id = self._create_tenant("recipient-group")
        self._create_recipient(tenant_id=tenant_id, group_key="ventas", destination="+573001110001")
        self._create_recipient(tenant_id=tenant_id, group_key="ventas", destination="+573001110002")
        rule = self._create_rule(
            tenant_id=tenant_id, recipient_strategy="configured_group", recipient_group_key="ventas"
        )
        service = NotificationRecipientService(self.db)
        result = service.resolve(tenant_id=tenant_id, rule=rule, payload={})
        self.assertEqual(result, ["+573001110001", "+573001110002"])

    def test_configured_group_from_other_tenant_does_not_appear(self):
        tenant_a = self._create_tenant("recipient-group-a")
        tenant_b = self._create_tenant("recipient-group-b")
        self._create_recipient(tenant_id=tenant_a, group_key="ventas", destination="+573001110001")
        rule = self._create_rule(
            tenant_id=tenant_b, recipient_strategy="configured_group", recipient_group_key="ventas"
        )
        service = NotificationRecipientService(self.db)
        result = service.resolve(tenant_id=tenant_b, rule=rule, payload={})
        self.assertEqual(result, [])

    def test_configured_group_deduplicates_destinations(self):
        tenant_id = self._create_tenant("recipient-dedupe")
        self._create_recipient(tenant_id=tenant_id, group_key="ventas", destination="+573001110001")
        self._create_recipient(tenant_id=tenant_id, group_key="ventas", destination=" +573001110001 ")
        rule = self._create_rule(
            tenant_id=tenant_id, recipient_strategy="configured_group", recipient_group_key="ventas"
        )
        service = NotificationRecipientService(self.db)
        result = service.resolve(tenant_id=tenant_id, rule=rule, payload={})
        self.assertEqual(result, ["+573001110001"])

    def test_event_field_resolves_allowed_path(self):
        tenant_id = self._create_tenant("recipient-event-field")
        rule = self._create_rule(
            tenant_id=tenant_id,
            recipient_strategy="event_field",
            recipient_group_key="custom.advisor_phone",
        )
        service = NotificationRecipientService(self.db)
        result = service.resolve(
            tenant_id=tenant_id, rule=rule, payload={"custom": {"advisor_phone": "+573002223344"}}
        )
        self.assertEqual(result, ["+573002223344"])

    def test_event_field_rejects_invalid_path(self):
        tenant_id = self._create_tenant("recipient-event-field-invalid")
        rule = self._create_rule(
            tenant_id=tenant_id,
            recipient_strategy="event_field",
            recipient_group_key="custom.__class__",
        )
        service = NotificationRecipientService(self.db)
        with self.assertRaises(NotificationRecipientResolutionError):
            service.resolve(tenant_id=tenant_id, rule=rule, payload={"custom": {}})

    def test_empty_destination_is_ignored(self):
        tenant_id = self._create_tenant("recipient-empty")
        rule = self._create_rule(tenant_id=tenant_id, recipient_strategy="event_customer")
        service = NotificationRecipientService(self.db)
        result = service.resolve(tenant_id=tenant_id, rule=rule, payload={"customer": {"phone": "   "}})
        self.assertEqual(result, [])

    def test_too_short_destination_is_ignored(self):
        tenant_id = self._create_tenant("recipient-short")
        rule = self._create_rule(tenant_id=tenant_id, recipient_strategy="event_customer")
        service = NotificationRecipientService(self.db)
        result = service.resolve(tenant_id=tenant_id, rule=rule, payload={"customer": {"phone": "12345"}})
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# Orquestador — 35 a 60
# ---------------------------------------------------------------------------
class NotificationOrchestratorTests(_BaseNotificationTestCase):
    def test_single_rule_creates_one_delivery(self):
        tenant_id = self._create_tenant("orch-single-rule")
        self._enable_capability(tenant_id)
        self._create_rule(tenant_id=tenant_id, name="regla-1")
        event = self._publish_event(
            tenant_id=tenant_id, idempotency_key="evt-1", payload=_valid_booking_payload()
        )
        orchestrator = NotificationOrchestrator(self.db)
        result = orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)
        self.assertEqual(result.created_count, 1)
        self.assertEqual(len(result.deliveries), 1)

    def test_multiple_rules_create_multiple_deliveries(self):
        tenant_id = self._create_tenant("orch-multi-rule")
        self._enable_capability(tenant_id)
        self._create_rule(tenant_id=tenant_id, name="regla-a", template_key="tpl-a")
        self._create_rule(tenant_id=tenant_id, name="regla-b", template_key="tpl-b")
        event = self._publish_event(
            tenant_id=tenant_id, idempotency_key="evt-2", payload=_valid_booking_payload()
        )
        orchestrator = NotificationOrchestrator(self.db)
        result = orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)
        self.assertEqual(result.created_count, 2)

    def test_group_with_three_recipients_creates_three_deliveries(self):
        tenant_id = self._create_tenant("orch-group-three")
        self._enable_capability(tenant_id)
        self._create_recipient(tenant_id=tenant_id, group_key="ventas", destination="+573001110001")
        self._create_recipient(tenant_id=tenant_id, group_key="ventas", destination="+573001110002")
        self._create_recipient(tenant_id=tenant_id, group_key="ventas", destination="+573001110003")
        self._create_rule(
            tenant_id=tenant_id,
            name="regla-grupo",
            recipient_strategy="configured_group",
            recipient_group_key="ventas",
        )
        event = self._publish_event(
            tenant_id=tenant_id, idempotency_key="evt-3", payload=_valid_booking_payload()
        )
        orchestrator = NotificationOrchestrator(self.db)
        result = orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)
        self.assertEqual(result.created_count, 3)

    def test_disabled_capability_creates_zero_deliveries(self):
        tenant_id = self._create_tenant("orch-cap-disabled")
        self._create_capability(tenant_id=tenant_id, enabled=False)
        self._create_rule(tenant_id=tenant_id, name="regla-1")
        event = self._publish_event(
            tenant_id=tenant_id, idempotency_key="evt-4", payload=_valid_booking_payload()
        )
        orchestrator = NotificationOrchestrator(self.db)
        result = orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)
        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.skipped_rule_count, 1)
        self.assertEqual(result.event.status, "processed")

    def test_false_condition_creates_zero_deliveries(self):
        tenant_id = self._create_tenant("orch-condition-false")
        self._enable_capability(tenant_id)
        self._create_rule(
            tenant_id=tenant_id,
            name="regla-condicion",
            conditions_json=[{"field": "booking.status", "operator": "equals", "value": "cancelled"}],
        )
        event = self._publish_event(
            tenant_id=tenant_id, idempotency_key="evt-5", payload=_valid_booking_payload()
        )
        orchestrator = NotificationOrchestrator(self.db)
        result = orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)
        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.skipped_rule_count, 1)

    def test_event_without_rules_is_processed(self):
        tenant_id = self._create_tenant("orch-no-rules")
        event = self._publish_event(
            tenant_id=tenant_id, idempotency_key="evt-6", payload=_valid_booking_payload()
        )
        orchestrator = NotificationOrchestrator(self.db)
        result = orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)
        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.event.status, "processed")

    def test_successful_event_is_processed(self):
        tenant_id = self._create_tenant("orch-success")
        self._enable_capability(tenant_id)
        self._create_rule(tenant_id=tenant_id, name="regla-ok")
        event = self._publish_event(
            tenant_id=tenant_id, idempotency_key="evt-7", payload=_valid_booking_payload()
        )
        orchestrator = NotificationOrchestrator(self.db)
        result = orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)
        self.assertEqual(result.event.status, "processed")
        self.assertIsNotNone(result.event.processed_at)

    def test_attempts_increments(self):
        tenant_id = self._create_tenant("orch-attempts")
        event = self._publish_event(
            tenant_id=tenant_id, idempotency_key="evt-8", payload=_valid_booking_payload()
        )
        self.assertEqual(event.attempts, 0)
        orchestrator = NotificationOrchestrator(self.db)
        result = orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)
        self.assertEqual(result.event.attempts, 1)

    def test_invalid_rule_marks_event_failed(self):
        tenant_id = self._create_tenant("orch-invalid-rule")
        self._enable_capability(tenant_id)
        self._create_rule(tenant_id=tenant_id, name="regla-invalida", channel="email")
        event = self._publish_event(
            tenant_id=tenant_id, idempotency_key="evt-9", payload=_valid_booking_payload()
        )
        orchestrator = NotificationOrchestrator(self.db)
        with self.assertRaises(NotificationRuleConfigurationError):
            orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)
        self.db.refresh(event)
        self.assertEqual(event.status, "failed")

    def test_stored_error_does_not_contain_recipient_or_payload(self):
        tenant_id = self._create_tenant("orch-safe-error")
        self._enable_capability(tenant_id)
        self._create_rule(tenant_id=tenant_id, name="regla-invalida", channel="email")
        event = self._publish_event(
            tenant_id=tenant_id,
            idempotency_key="evt-10",
            payload=_valid_booking_payload(customer={"phone": "+573009998877", "name": "Cliente Secreto"}),
        )
        orchestrator = NotificationOrchestrator(self.db)
        with self.assertRaises(NotificationRuleConfigurationError):
            orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)
        self.db.refresh(event)
        self.assertIsNotNone(event.last_error)
        self.assertNotIn("+573009998877", event.last_error)
        self.assertNotIn("Cliente Secreto", event.last_error)
        self.assertNotIn("booking", event.last_error)

    def test_reprocessing_processed_event_does_not_duplicate(self):
        tenant_id = self._create_tenant("orch-reprocess")
        self._enable_capability(tenant_id)
        self._create_rule(tenant_id=tenant_id, name="regla-reprocess")
        event = self._publish_event(
            tenant_id=tenant_id, idempotency_key="evt-11", payload=_valid_booking_payload()
        )
        orchestrator = NotificationOrchestrator(self.db)
        first = orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)
        second = orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)
        self.assertEqual(first.created_count, 1)
        self.assertEqual(second.created_count, 0)
        self.assertEqual(second.existing_count, 1)
        self.assertEqual(self.db.query(NotificationDelivery).count(), 1)

    def test_same_delivery_recovered_by_idempotency(self):
        tenant_id = self._create_tenant("orch-idempotent-delivery")
        self._enable_capability(tenant_id)
        self._create_rule(tenant_id=tenant_id, name="regla-idem")
        event = self._publish_event(
            tenant_id=tenant_id, idempotency_key="evt-12", payload=_valid_booking_payload()
        )
        orchestrator = NotificationOrchestrator(self.db)
        orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)

        # Forzamos un reintento (evento vuelve a un estado planificable).
        event.status = "failed"
        self.db.add(event)
        self.db.commit()

        result = orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)
        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.existing_count, 1)
        self.assertEqual(self.db.query(NotificationDelivery).count(), 1)

    def test_same_recipient_in_different_rules_creates_different_deliveries(self):
        tenant_id = self._create_tenant("orch-same-recipient-diff-rules")
        self._enable_capability(tenant_id)
        self._create_rule(tenant_id=tenant_id, name="regla-a", template_key="tpl-a")
        self._create_rule(tenant_id=tenant_id, name="regla-b", template_key="tpl-b")
        event = self._publish_event(
            tenant_id=tenant_id, idempotency_key="evt-13", payload=_valid_booking_payload()
        )
        orchestrator = NotificationOrchestrator(self.db)
        result = orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)
        self.assertEqual(result.created_count, 2)
        recipients = {delivery.recipient for delivery in result.deliveries}
        self.assertEqual(recipients, {"+573001112233"})
        idempotency_keys = {delivery.idempotency_key for delivery in result.deliveries}
        self.assertEqual(len(idempotency_keys), 2)

    def test_same_structure_isolated_across_tenants(self):
        tenant_a = self._create_tenant("orch-tenant-a")
        tenant_b = self._create_tenant("orch-tenant-b")
        for tenant_id in (tenant_a, tenant_b):
            self._enable_capability(tenant_id)
            self._create_rule(tenant_id=tenant_id, name="regla-comun")
        event_a = self._publish_event(
            tenant_id=tenant_a, idempotency_key="evt-shared", payload=_valid_booking_payload()
        )
        event_b = self._publish_event(
            tenant_id=tenant_b, idempotency_key="evt-shared", payload=_valid_booking_payload()
        )
        orchestrator = NotificationOrchestrator(self.db)
        result_a = orchestrator.plan_event(tenant_id=tenant_a, event_id=event_a.id, now=FIXED_NOW)
        result_b = orchestrator.plan_event(tenant_id=tenant_b, event_id=event_b.id, now=FIXED_NOW)
        self.assertEqual(result_a.created_count, 1)
        self.assertEqual(result_b.created_count, 1)
        self.assertNotEqual(result_a.deliveries[0].id, result_b.deliveries[0].id)

    def test_immediate_computes_correct_scheduled_time(self):
        tenant_id = self._create_tenant("orch-immediate-time")
        self._enable_capability(tenant_id)
        self._create_rule(tenant_id=tenant_id, name="regla-immediate")
        event = self._publish_event(
            tenant_id=tenant_id, idempotency_key="evt-14", payload=_valid_booking_payload()
        )
        orchestrator = NotificationOrchestrator(self.db)
        result = orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)
        delivery = result.deliveries[0]
        self.assertEqual(_naive(delivery.scheduled_for), _naive(FIXED_NOW))
        self.assertEqual(delivery.status, "pending")

    def test_future_available_at_is_respected(self):
        tenant_id = self._create_tenant("orch-future-available-at")
        self._enable_capability(tenant_id)
        self._create_rule(tenant_id=tenant_id, name="regla-future-avail")
        event = self._publish_event(
            tenant_id=tenant_id,
            idempotency_key="evt-15",
            payload=_valid_booking_payload(),
            available_at=FUTURE_AVAILABLE_AT,
        )
        orchestrator = NotificationOrchestrator(self.db)
        result = orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)
        self.assertEqual(_naive(result.deliveries[0].scheduled_for), _naive(FUTURE_AVAILABLE_AT))

    def test_future_reminder_stays_pending(self):
        tenant_id = self._create_tenant("orch-reminder-pending")
        self._enable_capability(tenant_id)
        self._create_rule(
            tenant_id=tenant_id,
            name="recordatorio-futuro",
            schedule_mode="relative_to_booking",
            schedule_offset_minutes=-60,
        )
        event = self._publish_event(
            tenant_id=tenant_id, idempotency_key="evt-16", payload=_valid_booking_payload()
        )
        orchestrator = NotificationOrchestrator(self.db)
        result = orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)
        delivery = result.deliveries[0]
        self.assertEqual(delivery.status, "pending")
        expected = datetime(2026, 8, 1, 14, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(_naive(delivery.scheduled_for), _naive(expected))

    def test_elapsed_reminder_is_skipped(self):
        tenant_id = self._create_tenant("orch-reminder-skipped")
        self._enable_capability(tenant_id)
        self._create_rule(
            tenant_id=tenant_id,
            name="recordatorio-vencido",
            schedule_mode="relative_to_booking",
            schedule_offset_minutes=-600,
        )
        event = self._publish_event(
            tenant_id=tenant_id, idempotency_key="evt-17", payload=_valid_booking_payload()
        )
        orchestrator = NotificationOrchestrator(self.db)
        result = orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)
        self.assertEqual(result.deliveries[0].status, "skipped")

    def test_skipped_delivery_contains_safe_reason(self):
        tenant_id = self._create_tenant("orch-reminder-safe-reason")
        self._enable_capability(tenant_id)
        self._create_rule(
            tenant_id=tenant_id,
            name="recordatorio-vencido-reason",
            schedule_mode="relative_to_booking",
            schedule_offset_minutes=-600,
        )
        event = self._publish_event(
            tenant_id=tenant_id, idempotency_key="evt-18", payload=_valid_booking_payload()
        )
        orchestrator = NotificationOrchestrator(self.db)
        result = orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)
        metadata = result.deliveries[0].metadata_json
        self.assertEqual(
            metadata,
            {
                "reason": "scheduled_time_elapsed",
                "action_type": "send_whatsapp_template",
                "schedule_mode": "relative_to_booking",
            },
        )
        self.assertNotIn("573001112233", str(metadata))

    def test_processing_event_is_rejected(self):
        tenant_id = self._create_tenant("orch-processing-rejected")
        event = self._publish_event(
            tenant_id=tenant_id, idempotency_key="evt-19", payload=_valid_booking_payload()
        )
        event.status = "processing"
        self.db.add(event)
        self.db.commit()
        orchestrator = NotificationOrchestrator(self.db)
        with self.assertRaises(NotificationEventProcessingError):
            orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)

    def test_missing_event_is_rejected(self):
        tenant_id = self._create_tenant("orch-missing-event")
        orchestrator = NotificationOrchestrator(self.db)
        with self.assertRaises(NotificationEventProcessingError):
            orchestrator.plan_event(tenant_id=tenant_id, event_id="does-not-exist", now=FIXED_NOW)

    def test_event_from_other_tenant_cannot_be_processed(self):
        tenant_a = self._create_tenant("orch-cross-tenant-a")
        tenant_b = self._create_tenant("orch-cross-tenant-b")
        event = self._publish_event(
            tenant_id=tenant_a, idempotency_key="evt-20", payload=_valid_booking_payload()
        )
        orchestrator = NotificationOrchestrator(self.db)
        with self.assertRaises(NotificationEventProcessingError):
            orchestrator.plan_event(tenant_id=tenant_b, event_id=event.id, now=FIXED_NOW)

    def test_delivery_integrity_error_recovery(self):
        tenant_id = self._create_tenant("orch-delivery-race")
        self._enable_capability(tenant_id)
        rule = self._create_rule(tenant_id=tenant_id, name="regla-race")
        event = self._publish_event(
            tenant_id=tenant_id, idempotency_key="evt-21", payload=_valid_booking_payload()
        )

        orchestrator = NotificationOrchestrator(self.db)
        idempotency_key = orchestrator._build_idempotency_key(
            event_id=event.id, rule_id=rule.id, channel="whatsapp", recipient="+573001112233"
        )
        existing_delivery = NotificationDelivery(
            tenant_id=tenant_id,
            domain_event_id=event.id,
            notification_rule_id=rule.id,
            channel="whatsapp",
            recipient="+573001112233",
            template_key=rule.template_key,
            status="pending",
            scheduled_for=FIXED_NOW,
            idempotency_key=idempotency_key,
            metadata_json={},
        )
        self.db.add(existing_delivery)
        self.db.commit()
        self.db.refresh(existing_delivery)

        call_state = {"count": 0}
        original_lookup = NotificationOrchestrator._get_delivery_by_key

        def flaky_lookup(self_orch, *, tenant_id, idempotency_key):
            call_state["count"] += 1
            if call_state["count"] == 1:
                return None
            return original_lookup(self_orch, tenant_id=tenant_id, idempotency_key=idempotency_key)

        with patch.object(NotificationOrchestrator, "_get_delivery_by_key", flaky_lookup):
            result = orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)

        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.existing_count, 1)
        self.assertEqual(result.deliveries[0].id, existing_delivery.id)
        self.assertEqual(self.db.query(NotificationDelivery).count(), 1)

    def test_session_usable_after_delivery_conflict(self):
        tenant_id = self._create_tenant("orch-delivery-conflict")
        self._enable_capability(tenant_id)
        rule = self._create_rule(tenant_id=tenant_id, name="regla-conflict", template_key="tpl-real")
        event = self._publish_event(
            tenant_id=tenant_id, idempotency_key="evt-22", payload=_valid_booking_payload()
        )

        orchestrator = NotificationOrchestrator(self.db)
        idempotency_key = orchestrator._build_idempotency_key(
            event_id=event.id, rule_id=rule.id, channel="whatsapp", recipient="+573001112233"
        )
        conflicting_delivery = NotificationDelivery(
            tenant_id=tenant_id,
            domain_event_id=event.id,
            notification_rule_id=rule.id,
            channel="whatsapp",
            recipient="+573001112233",
            template_key="tpl-different",
            status="pending",
            scheduled_for=FIXED_NOW,
            idempotency_key=idempotency_key,
            metadata_json={},
        )
        self.db.add(conflicting_delivery)
        self.db.commit()

        with self.assertRaises(NotificationEventProcessingError):
            orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)

        self.db.refresh(event)
        self.assertEqual(event.status, "failed")

        # La sesion sigue siendo utilizable tras el conflicto.
        other_event = self._publish_event(
            tenant_id=tenant_id, idempotency_key="evt-22b", payload=_valid_booking_payload()
        )
        self.assertIsNotNone(other_event.id)
        self.assertEqual(
            self.db.query(DomainEvent).filter(DomainEvent.tenant_id == tenant_id).count(), 2
        )

    def test_no_crm_whatsapp_messages_created(self):
        tenant_id = self._create_tenant("orch-no-crm-messages")
        self._enable_capability(tenant_id)
        self._create_rule(tenant_id=tenant_id, name="regla-no-crm")
        event = self._publish_event(
            tenant_id=tenant_id, idempotency_key="evt-23", payload=_valid_booking_payload()
        )
        orchestrator = NotificationOrchestrator(self.db)
        orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)
        self.assertEqual(self.db.query(CrmWhatsAppMessage).count(), 0)

    # Phase 6 — next_attempt_at bookkeeping ---------------------------------
    def test_pending_delivery_gets_next_attempt_at_equal_to_scheduled_for(self):
        tenant_id = self._create_tenant("orch-next-attempt-pending")
        self._enable_capability(tenant_id)
        self._create_rule(tenant_id=tenant_id, name="regla-next-attempt")
        event = self._publish_event(
            tenant_id=tenant_id, idempotency_key="evt-next-1", payload=_valid_booking_payload()
        )
        orchestrator = NotificationOrchestrator(self.db)
        result = orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)
        delivery = result.deliveries[0]
        self.assertEqual(delivery.status, "pending")
        self.assertEqual(_naive(delivery.next_attempt_at), _naive(delivery.scheduled_for))

    def test_skipped_delivery_has_no_next_attempt_at(self):
        tenant_id = self._create_tenant("orch-next-attempt-skipped")
        self._enable_capability(tenant_id)
        self._create_rule(
            tenant_id=tenant_id,
            name="recordatorio-vencido-next-attempt",
            schedule_mode="relative_to_booking",
            schedule_offset_minutes=-600,
        )
        event = self._publish_event(
            tenant_id=tenant_id, idempotency_key="evt-next-2", payload=_valid_booking_payload()
        )
        orchestrator = NotificationOrchestrator(self.db)
        result = orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)
        delivery = result.deliveries[0]
        self.assertEqual(delivery.status, "skipped")
        self.assertIsNone(delivery.next_attempt_at)

    def test_reconciling_pending_delivery_backfills_missing_next_attempt_at(self):
        tenant_id = self._create_tenant("orch-next-attempt-backfill")
        self._enable_capability(tenant_id)
        self._create_rule(tenant_id=tenant_id, name="regla-backfill")
        event = self._publish_event(
            tenant_id=tenant_id, idempotency_key="evt-next-3", payload=_valid_booking_payload()
        )
        orchestrator = NotificationOrchestrator(self.db)
        first = orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)
        delivery = first.deliveries[0]
        delivery.next_attempt_at = None
        self.db.add(delivery)
        self.db.commit()

        # Force replanning by resetting the event back to pending, simulating
        # a reconciliation path that revisits an existing delivery.
        event_row = self.db.query(DomainEvent).filter(DomainEvent.id == event.id).first()
        event_row.status = "pending"
        self.db.add(event_row)
        self.db.commit()

        second = orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=FIXED_NOW)
        reconciled = second.deliveries[0]
        self.assertIsNotNone(reconciled.next_attempt_at)
        self.assertEqual(_naive(reconciled.next_attempt_at), _naive(reconciled.scheduled_for))

    def test_no_external_service_is_called(self):
        forbidden_tokens = ("httpx", "requests", "boto3", "urllib", "socket.")
        for path in _PHASE3_SOURCE_FILES:
            content = path.read_text(encoding="utf-8")
            for token in forbidden_tokens:
                self.assertNotIn(token, content)


if __name__ == "__main__":
    unittest.main()
