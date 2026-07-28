import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

TEST_DB_PATH = Path("serviai_notification_schedule_reconciliation_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.identity import Tenant
from app.models.notifications import DomainEvent, NotificationDelivery, TenantNotificationRule
from app.services.domain_event_service import DomainEventService
from app.services.notification_schedule_reconciliation_service import (
    NotificationScheduleReconciliationService,
)

FIXED_NOW = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)


class _BaseReconciliationTestCase(unittest.TestCase):
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
        self.service = NotificationScheduleReconciliationService(self.db)
        self.events = DomainEventService(self.db)

    def tearDown(self):
        self.db.close()

    def _create_tenant(self, slug: str = "reconcile-tenant") -> str:
        tenant = Tenant(name=f"Empresa {slug}", slug=f"{slug}-{uuid4().hex[:8]}")
        self.db.add(tenant)
        self.db.commit()
        self.db.refresh(tenant)
        return tenant.id

    def _rule(self, tenant_id: str) -> TenantNotificationRule:
        rule = TenantNotificationRule(
            tenant_id=tenant_id,
            name=f"rule-{uuid4().hex[:8]}",
            capability_key="booking_notifications",
            event_type="booking.created",
            channel="whatsapp",
            action_type="send_whatsapp_template",
            template_key="tpl",
            recipient_strategy="event_customer",
            conditions_json=[],
            variable_mapping_json={},
        )
        self.db.add(rule)
        self.db.commit()
        self.db.refresh(rule)
        return rule

    def _publish_event(
        self, tenant_id: str, *, event_type: str, resource_id: str, offset_seconds: int, resource_type: str = "crm_booking"
    ) -> DomainEvent:
        if resource_type == "crm_booking":
            payload = {
                "booking": {
                    "id": resource_id,
                    "status": "confirmed",
                    "start_at": "2026-08-10T15:00:00+00:00",
                    "timezone": "America/Bogota",
                }
            }
        else:
            payload = {
                "call": {
                    "id": resource_id,
                    "provider": "ultravox",
                    "status": "completed",
                }
            }
        result = self.events.publish(
            tenant_id=tenant_id,
            event_type=event_type,
            source="test",
            idempotency_key=f"evt-{uuid4().hex[:8]}",
            payload=payload,
            resource_type=resource_type,
            resource_id=resource_id,
            available_at=FIXED_NOW,
        )
        event = result.event
        event.created_at = FIXED_NOW + timedelta(seconds=offset_seconds)
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def _create_delivery(
        self, tenant_id: str, event: DomainEvent, rule: TenantNotificationRule, *, status: str = "pending"
    ) -> NotificationDelivery:
        delivery = NotificationDelivery(
            tenant_id=tenant_id,
            domain_event_id=event.id,
            notification_rule_id=rule.id,
            channel="whatsapp",
            recipient="+573001112233",
            status=status,
            scheduled_for=FIXED_NOW,
            next_attempt_at=FIXED_NOW if status == "pending" else None,
            attempts=0,
            idempotency_key=f"delivery-{uuid4().hex[:8]}",
            metadata_json={},
        )
        self.db.add(delivery)
        self.db.commit()
        self.db.refresh(delivery)
        return delivery


class CancellationReconciliationTests(_BaseReconciliationTestCase):
    def test_cancellation_cancels_prior_pending(self):
        tenant_id = self._create_tenant()
        rule = self._rule(tenant_id)
        booking_id = "bk-1"
        created = self._publish_event(tenant_id, event_type="booking.created", resource_id=booking_id, offset_seconds=0)
        delivery = self._create_delivery(tenant_id, created, rule, status="pending")
        cancelled_event = self._publish_event(
            tenant_id, event_type="booking.cancelled", resource_id=booking_id, offset_seconds=10
        )

        result = self.service.reconcile_for_event(tenant_id=tenant_id, event_id=cancelled_event.id, now=FIXED_NOW)

        self.assertEqual(result.status, "applied")
        self.assertEqual(result.cancelled_count, 1)
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "cancelled")
        self.assertEqual(delivery.error_message, "booking_cancelled")

    def test_cancellation_cancels_prior_failed(self):
        tenant_id = self._create_tenant()
        rule = self._rule(tenant_id)
        booking_id = "bk-2"
        created = self._publish_event(tenant_id, event_type="booking.created", resource_id=booking_id, offset_seconds=0)
        delivery = self._create_delivery(tenant_id, created, rule, status="failed")
        cancelled_event = self._publish_event(
            tenant_id, event_type="booking.cancelled", resource_id=booking_id, offset_seconds=10
        )

        self.service.reconcile_for_event(tenant_id=tenant_id, event_id=cancelled_event.id, now=FIXED_NOW)

        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "cancelled")

    def test_cancellation_does_not_modify_sent(self):
        tenant_id = self._create_tenant()
        rule = self._rule(tenant_id)
        booking_id = "bk-3"
        created = self._publish_event(tenant_id, event_type="booking.created", resource_id=booking_id, offset_seconds=0)
        delivery = self._create_delivery(tenant_id, created, rule, status="sent")
        cancelled_event = self._publish_event(
            tenant_id, event_type="booking.cancelled", resource_id=booking_id, offset_seconds=10
        )

        result = self.service.reconcile_for_event(tenant_id=tenant_id, event_id=cancelled_event.id, now=FIXED_NOW)

        self.assertEqual(result.cancelled_count, 0)
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "sent")

    def test_cancellation_flags_processing_with_cancel_requested(self):
        tenant_id = self._create_tenant()
        rule = self._rule(tenant_id)
        booking_id = "bk-4"
        created = self._publish_event(tenant_id, event_type="booking.created", resource_id=booking_id, offset_seconds=0)
        delivery = self._create_delivery(tenant_id, created, rule, status="processing")
        cancelled_event = self._publish_event(
            tenant_id, event_type="booking.cancelled", resource_id=booking_id, offset_seconds=10
        )

        result = self.service.reconcile_for_event(tenant_id=tenant_id, event_id=cancelled_event.id, now=FIXED_NOW)

        self.assertEqual(result.flagged_count, 1)
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "processing")
        self.assertTrue(delivery.metadata_json.get("cancel_requested"))
        self.assertEqual(delivery.metadata_json.get("cancel_reason"), "booking_cancelled")

    def test_next_attempt_at_is_cleared_on_cancellation(self):
        tenant_id = self._create_tenant()
        rule = self._rule(tenant_id)
        booking_id = "bk-5"
        created = self._publish_event(tenant_id, event_type="booking.created", resource_id=booking_id, offset_seconds=0)
        delivery = self._create_delivery(tenant_id, created, rule, status="pending")
        cancelled_event = self._publish_event(
            tenant_id, event_type="booking.cancelled", resource_id=booking_id, offset_seconds=10
        )

        self.service.reconcile_for_event(tenant_id=tenant_id, event_id=cancelled_event.id, now=FIXED_NOW)

        self.db.refresh(delivery)
        self.assertIsNone(delivery.next_attempt_at)


class RescheduleReconciliationTests(_BaseReconciliationTestCase):
    def test_reschedule_cancels_prior_created(self):
        tenant_id = self._create_tenant()
        rule = self._rule(tenant_id)
        booking_id = "bk-6"
        created = self._publish_event(tenant_id, event_type="booking.created", resource_id=booking_id, offset_seconds=0)
        delivery = self._create_delivery(tenant_id, created, rule, status="pending")
        rescheduled_event = self._publish_event(
            tenant_id, event_type="booking.rescheduled", resource_id=booking_id, offset_seconds=10
        )

        result = self.service.reconcile_for_event(tenant_id=tenant_id, event_id=rescheduled_event.id, now=FIXED_NOW)

        self.assertEqual(result.cancelled_count, 1)
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "cancelled")
        self.assertEqual(delivery.error_message, "booking_schedule_superseded")

    def test_reschedule_cancels_prior_reschedule(self):
        tenant_id = self._create_tenant()
        rule = self._rule(tenant_id)
        booking_id = "bk-7"
        self._publish_event(tenant_id, event_type="booking.created", resource_id=booking_id, offset_seconds=0)
        first_reschedule = self._publish_event(
            tenant_id, event_type="booking.rescheduled", resource_id=booking_id, offset_seconds=10
        )
        delivery = self._create_delivery(tenant_id, first_reschedule, rule, status="pending")
        second_reschedule = self._publish_event(
            tenant_id, event_type="booking.rescheduled", resource_id=booking_id, offset_seconds=20
        )

        self.service.reconcile_for_event(tenant_id=tenant_id, event_id=second_reschedule.id, now=FIXED_NOW)

        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "cancelled")

    def test_reschedule_preserves_current_event_deliveries(self):
        tenant_id = self._create_tenant()
        rule = self._rule(tenant_id)
        booking_id = "bk-8"
        self._publish_event(tenant_id, event_type="booking.created", resource_id=booking_id, offset_seconds=0)
        rescheduled_event = self._publish_event(
            tenant_id, event_type="booking.rescheduled", resource_id=booking_id, offset_seconds=10
        )
        current_delivery = self._create_delivery(tenant_id, rescheduled_event, rule, status="pending")

        self.service.reconcile_for_event(tenant_id=tenant_id, event_id=rescheduled_event.id, now=FIXED_NOW)

        self.db.refresh(current_delivery)
        self.assertEqual(current_delivery.status, "pending")

    def test_new_reschedule_does_not_prevent_new_reminders(self):
        tenant_id = self._create_tenant()
        rule = self._rule(tenant_id)
        booking_id = "bk-9"
        self._publish_event(tenant_id, event_type="booking.created", resource_id=booking_id, offset_seconds=0)
        rescheduled_event = self._publish_event(
            tenant_id, event_type="booking.rescheduled", resource_id=booking_id, offset_seconds=10
        )
        self.service.reconcile_for_event(tenant_id=tenant_id, event_id=rescheduled_event.id, now=FIXED_NOW)
        new_delivery = self._create_delivery(tenant_id, rescheduled_event, rule, status="pending")
        self.db.refresh(new_delivery)
        self.assertEqual(new_delivery.status, "pending")


class ScopeAndIdempotencyTests(_BaseReconciliationTestCase):
    def test_other_tenant_is_not_modified(self):
        tenant_a = self._create_tenant("a")
        tenant_b = self._create_tenant("b")
        rule_b = self._rule(tenant_b)
        booking_id = "bk-shared"
        created_b = self._publish_event(tenant_b, event_type="booking.created", resource_id=booking_id, offset_seconds=0)
        delivery_b = self._create_delivery(tenant_b, created_b, rule_b, status="pending")

        rule_a = self._rule(tenant_a)
        created_a = self._publish_event(tenant_a, event_type="booking.created", resource_id=booking_id, offset_seconds=0)
        self._create_delivery(tenant_a, created_a, rule_a, status="pending")
        cancelled_a = self._publish_event(tenant_a, event_type="booking.cancelled", resource_id=booking_id, offset_seconds=10)

        self.service.reconcile_for_event(tenant_id=tenant_a, event_id=cancelled_a.id, now=FIXED_NOW)

        self.db.refresh(delivery_b)
        self.assertEqual(delivery_b.status, "pending")

    def test_other_booking_is_not_modified(self):
        tenant_id = self._create_tenant()
        rule = self._rule(tenant_id)
        other_created = self._publish_event(tenant_id, event_type="booking.created", resource_id="bk-other", offset_seconds=0)
        other_delivery = self._create_delivery(tenant_id, other_created, rule, status="pending")

        created = self._publish_event(tenant_id, event_type="booking.created", resource_id="bk-target", offset_seconds=0)
        self._create_delivery(tenant_id, created, rule, status="pending")
        cancelled = self._publish_event(tenant_id, event_type="booking.cancelled", resource_id="bk-target", offset_seconds=10)

        self.service.reconcile_for_event(tenant_id=tenant_id, event_id=cancelled.id, now=FIXED_NOW)

        self.db.refresh(other_delivery)
        self.assertEqual(other_delivery.status, "pending")

    def test_call_event_is_a_no_op(self):
        tenant_id = self._create_tenant()
        call_event = self._publish_event(
            tenant_id, event_type="call.completed", resource_id="call-1", offset_seconds=0, resource_type="crm_voice_call"
        )
        result = self.service.reconcile_for_event(tenant_id=tenant_id, event_id=call_event.id, now=FIXED_NOW)
        self.assertEqual(result.status, "not_applicable")

    def test_booking_created_is_a_no_op(self):
        tenant_id = self._create_tenant()
        created = self._publish_event(tenant_id, event_type="booking.created", resource_id="bk-noop", offset_seconds=0)
        result = self.service.reconcile_for_event(tenant_id=tenant_id, event_id=created.id, now=FIXED_NOW)
        self.assertEqual(result.status, "not_applicable")

    def test_reconciliation_is_idempotent(self):
        tenant_id = self._create_tenant()
        rule = self._rule(tenant_id)
        booking_id = "bk-idempotent"
        created = self._publish_event(tenant_id, event_type="booking.created", resource_id=booking_id, offset_seconds=0)
        delivery = self._create_delivery(tenant_id, created, rule, status="pending")
        cancelled = self._publish_event(tenant_id, event_type="booking.cancelled", resource_id=booking_id, offset_seconds=10)

        first = self.service.reconcile_for_event(tenant_id=tenant_id, event_id=cancelled.id, now=FIXED_NOW)
        second = self.service.reconcile_for_event(tenant_id=tenant_id, event_id=cancelled.id, now=FIXED_NOW)

        self.assertEqual(first.cancelled_count, 1)
        self.assertEqual(second.cancelled_count, 0)
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "cancelled")

    def test_unknown_event_returns_not_applicable(self):
        tenant_id = self._create_tenant()
        result = self.service.reconcile_for_event(tenant_id=tenant_id, event_id="missing", now=FIXED_NOW)
        self.assertEqual(result.status, "not_applicable")


if __name__ == "__main__":
    unittest.main()
