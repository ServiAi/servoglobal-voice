import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

TEST_DB_PATH = Path("serviai_notification_retry_policy_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.identity import Tenant
from app.models.notifications import DomainEvent, NotificationDelivery, TenantNotificationRule
from app.services.notification_retry_policy import NotificationRetryDecision, NotificationRetryPolicy

FIXED_NOW = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)


class _BaseRetryPolicyTestCase(unittest.TestCase):
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

    def _create_tenant(self, slug: str = "retry-tenant") -> str:
        tenant = Tenant(name=f"Empresa {slug}", slug=f"{slug}-{uuid4().hex[:8]}")
        self.db.add(tenant)
        self.db.commit()
        self.db.refresh(tenant)
        return tenant.id

    def _create_delivery(self, tenant_id: str, *, attempts: int = 1, status: str = "processing") -> NotificationDelivery:
        event = DomainEvent(
            tenant_id=tenant_id,
            event_type="booking.created",
            source="test",
            idempotency_key=f"evt-{uuid4().hex[:8]}",
            payload_json={},
            available_at=FIXED_NOW,
        )
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
        self.db.add_all([event, rule])
        self.db.commit()
        self.db.refresh(event)
        self.db.refresh(rule)
        delivery = NotificationDelivery(
            tenant_id=tenant_id,
            domain_event_id=event.id,
            notification_rule_id=rule.id,
            channel="whatsapp",
            recipient="+573001112233",
            status=status,
            scheduled_for=FIXED_NOW,
            attempts=attempts,
            idempotency_key=f"delivery-{uuid4().hex[:8]}",
            metadata_json={},
            claim_token="tok-123",
            claimed_at=FIXED_NOW,
            claim_expires_at=FIXED_NOW,
        )
        self.db.add(delivery)
        self.db.commit()
        self.db.refresh(delivery)
        return delivery

    def _policy(self, *, base=30, max_seconds=3600, jitter=0, jitter_fn=None) -> NotificationRetryPolicy:
        return NotificationRetryPolicy(
            self.db,
            base_retry_seconds=base,
            max_retry_seconds=max_seconds,
            jitter_seconds=jitter,
            jitter_fn=jitter_fn,
        )


class BackoffComputationTests(_BaseRetryPolicyTestCase):
    def test_first_retry_uses_base_delay(self):
        policy = self._policy(base=30, jitter=0, jitter_fn=lambda: 0)
        self.assertEqual(policy.compute_delay_seconds(attempts=1), 30)

    def test_second_retry_doubles_delay(self):
        policy = self._policy(base=30, jitter=0, jitter_fn=lambda: 0)
        self.assertEqual(policy.compute_delay_seconds(attempts=2), 60)

    def test_third_retry_doubles_again(self):
        policy = self._policy(base=30, jitter=0, jitter_fn=lambda: 0)
        self.assertEqual(policy.compute_delay_seconds(attempts=3), 120)

    def test_delay_is_capped_at_max(self):
        policy = self._policy(base=30, max_seconds=100, jitter=0, jitter_fn=lambda: 0)
        self.assertEqual(policy.compute_delay_seconds(attempts=10), 100)

    def test_jitter_minimum_is_zero(self):
        policy = self._policy(base=30, jitter=10, jitter_fn=lambda: -5)
        self.assertEqual(policy.compute_delay_seconds(attempts=1), 30)

    def test_jitter_maximum_is_clamped(self):
        policy = self._policy(base=30, jitter=10, jitter_fn=lambda: 999)
        self.assertEqual(policy.compute_delay_seconds(attempts=1), 40)

    def test_jitter_zero_is_deterministic(self):
        policy = self._policy(base=30, jitter=10, jitter_fn=lambda: 0)
        self.assertEqual(policy.compute_delay_seconds(attempts=1), 30)

    def test_attempts_zero_behaves_like_attempts_one(self):
        policy = self._policy(base=30, jitter=0, jitter_fn=lambda: 0)
        self.assertEqual(policy.compute_delay_seconds(attempts=0), 30)


class ApplyFailureTests(_BaseRetryPolicyTestCase):
    def test_now_must_be_timezone_aware(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id)
        policy = self._policy(jitter_fn=lambda: 0)
        with self.assertRaises(ValueError):
            policy.apply_failure(
                tenant_id=tenant_id,
                delivery_id=delivery.id,
                now=datetime(2026, 8, 1, 10, 0, 0),
                error_code="whatsapp_provider_send_failed",
                retryable=True,
                max_attempts=5,
            )

    def test_retryable_failure_schedules_retry(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, attempts=1)
        policy = self._policy(base=30, jitter=0, jitter_fn=lambda: 0)
        decision = policy.apply_failure(
            tenant_id=tenant_id,
            delivery_id=delivery.id,
            now=FIXED_NOW,
            error_code="whatsapp_provider_send_failed",
            retryable=True,
            max_attempts=5,
        )
        self.assertEqual(decision.action, "retry")
        self.assertEqual(decision.status, "failed")
        self.assertIsNotNone(decision.next_attempt_at)

    def test_retry_conserves_failed_status_on_delivery(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, attempts=1)
        policy = self._policy(jitter_fn=lambda: 0)
        policy.apply_failure(
            tenant_id=tenant_id, delivery_id=delivery.id, now=FIXED_NOW,
            error_code="whatsapp_provider_send_failed", retryable=True, max_attempts=5,
        )
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "failed")

    def test_retry_updates_next_attempt_at(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, attempts=1)
        policy = self._policy(base=30, jitter=0, jitter_fn=lambda: 0)
        policy.apply_failure(
            tenant_id=tenant_id, delivery_id=delivery.id, now=FIXED_NOW,
            error_code="whatsapp_provider_send_failed", retryable=True, max_attempts=5,
        )
        self.db.refresh(delivery)
        stored = delivery.next_attempt_at
        if stored.tzinfo is None:
            stored = stored.replace(tzinfo=timezone.utc)
        self.assertEqual(stored, FIXED_NOW.replace(second=30))

    def test_retry_clears_claim_fields(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, attempts=1)
        policy = self._policy(jitter_fn=lambda: 0)
        policy.apply_failure(
            tenant_id=tenant_id, delivery_id=delivery.id, now=FIXED_NOW,
            error_code="whatsapp_provider_send_failed", retryable=True, max_attempts=5,
        )
        self.db.refresh(delivery)
        self.assertIsNone(delivery.claim_token)
        self.assertIsNone(delivery.claimed_at)
        self.assertIsNone(delivery.claim_expires_at)

    def test_error_code_stored_is_a_safe_code(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, attempts=1)
        policy = self._policy(jitter_fn=lambda: 0)
        policy.apply_failure(
            tenant_id=tenant_id, delivery_id=delivery.id, now=FIXED_NOW,
            error_code="whatsapp_provider_send_failed", retryable=True, max_attempts=5,
        )
        self.db.refresh(delivery)
        self.assertEqual(delivery.error_message, "whatsapp_provider_send_failed")

    def test_max_attempts_reached_produces_dead_letter(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, attempts=5)
        policy = self._policy(jitter_fn=lambda: 0)
        decision = policy.apply_failure(
            tenant_id=tenant_id, delivery_id=delivery.id, now=FIXED_NOW,
            error_code="whatsapp_provider_send_failed", retryable=True, max_attempts=5,
        )
        self.assertEqual(decision.action, "dead_letter")
        self.assertEqual(decision.error_code, "retry_attempts_exhausted")
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "dead_letter")

    def test_permanent_failure_produces_dead_letter(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, attempts=1)
        policy = self._policy(jitter_fn=lambda: 0)
        decision = policy.apply_failure(
            tenant_id=tenant_id, delivery_id=delivery.id, now=FIXED_NOW,
            error_code="tenant_mismatch", retryable=False, max_attempts=5,
        )
        self.assertEqual(decision.action, "dead_letter")
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "dead_letter")

    def test_non_retryable_error_code_forces_dead_letter_even_if_retryable_true(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, attempts=1)
        policy = self._policy(jitter_fn=lambda: 0)
        decision = policy.apply_failure(
            tenant_id=tenant_id, delivery_id=delivery.id, now=FIXED_NOW,
            error_code="template_variable_missing", retryable=True, max_attempts=5,
        )
        self.assertEqual(decision.action, "dead_letter")

    def test_dead_letter_has_no_next_attempt(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, attempts=5)
        policy = self._policy(jitter_fn=lambda: 0)
        policy.apply_failure(
            tenant_id=tenant_id, delivery_id=delivery.id, now=FIXED_NOW,
            error_code="whatsapp_provider_send_failed", retryable=True, max_attempts=5,
        )
        self.db.refresh(delivery)
        self.assertIsNone(delivery.next_attempt_at)

    def test_wrong_tenant_does_not_modify_delivery(self):
        tenant_id = self._create_tenant("owner")
        other_tenant_id = self._create_tenant("other")
        delivery = self._create_delivery(tenant_id, attempts=1)
        policy = self._policy(jitter_fn=lambda: 0)
        with self.assertRaises(ValueError):
            policy.apply_failure(
                tenant_id=other_tenant_id, delivery_id=delivery.id, now=FIXED_NOW,
                error_code="whatsapp_provider_send_failed", retryable=True, max_attempts=5,
            )
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "processing")

    def test_unknown_delivery_raises(self):
        tenant_id = self._create_tenant()
        policy = self._policy(jitter_fn=lambda: 0)
        with self.assertRaises(ValueError):
            policy.apply_failure(
                tenant_id=tenant_id, delivery_id="missing", now=FIXED_NOW,
                error_code="whatsapp_provider_send_failed", retryable=True, max_attempts=5,
            )

    def test_decision_is_frozen_dataclass(self):
        decision = NotificationRetryDecision(
            action="retry", next_attempt_at=FIXED_NOW, status="failed", error_code="x"
        )
        with self.assertRaises(Exception):
            decision.action = "dead_letter"

    def test_failed_at_is_set_on_retry(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, attempts=1)
        policy = self._policy(jitter_fn=lambda: 0)
        policy.apply_failure(
            tenant_id=tenant_id, delivery_id=delivery.id, now=FIXED_NOW,
            error_code="whatsapp_provider_send_failed", retryable=True, max_attempts=5,
        )
        self.db.refresh(delivery)
        stored = delivery.failed_at
        if stored.tzinfo is None:
            stored = stored.replace(tzinfo=timezone.utc)
        self.assertEqual(stored, FIXED_NOW)


class StaleOwnerProtectionTests(_BaseRetryPolicyTestCase):
    def _set_delivery(self, delivery, **fields):
        self.db.query(NotificationDelivery).filter(NotificationDelivery.id == delivery.id).update(fields)
        self.db.commit()
        self.db.refresh(delivery)

    def test_correct_token_allows_retry_to_apply(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, attempts=1, status="processing")
        self._set_delivery(delivery, claim_token="tok-current")
        policy = self._policy(jitter_fn=lambda: 0)
        decision = policy.apply_failure(
            tenant_id=tenant_id, delivery_id=delivery.id, now=FIXED_NOW,
            error_code="whatsapp_provider_send_failed", retryable=True, max_attempts=5,
            expected_claim_token="tok-current", allowed_current_statuses={"processing", "failed"},
        )
        self.assertEqual(decision.action, "retry")
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "failed")

    def test_wrong_token_returns_stale_owner(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, attempts=1, status="processing")
        self._set_delivery(delivery, claim_token="tok-current")
        policy = self._policy(jitter_fn=lambda: 0)
        decision = policy.apply_failure(
            tenant_id=tenant_id, delivery_id=delivery.id, now=FIXED_NOW,
            error_code="whatsapp_provider_send_failed", retryable=True, max_attempts=5,
            expected_claim_token="tok-stale", allowed_current_statuses={"processing", "failed"},
        )
        self.assertEqual(decision.action, "stale_owner")
        self.assertEqual(decision.error_code, "stale_delivery_owner")
        self.assertEqual(decision.status, "processing")

    def test_wrong_token_does_not_modify_delivery(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, attempts=1, status="processing")
        self._set_delivery(delivery, claim_token="tok-current", error_message=None)
        policy = self._policy(jitter_fn=lambda: 0)
        policy.apply_failure(
            tenant_id=tenant_id, delivery_id=delivery.id, now=FIXED_NOW,
            error_code="whatsapp_provider_send_failed", retryable=True, max_attempts=5,
            expected_claim_token="tok-stale", allowed_current_statuses={"processing", "failed"},
        )
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "processing")
        self.assertEqual(delivery.claim_token, "tok-current")
        self.assertIsNone(delivery.error_message)
        self.assertIsNone(delivery.failed_at)

    def test_old_token_does_not_clear_new_token(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, attempts=1, status="processing")
        self._set_delivery(delivery, claim_token="tok-new")
        policy = self._policy(jitter_fn=lambda: 0)
        policy.apply_failure(
            tenant_id=tenant_id, delivery_id=delivery.id, now=FIXED_NOW,
            error_code="whatsapp_provider_send_failed", retryable=True, max_attempts=5,
            expected_claim_token="tok-old", allowed_current_statuses={"processing", "failed"},
        )
        self.db.refresh(delivery)
        self.assertEqual(delivery.claim_token, "tok-new")

    def test_sent_is_never_downgraded_to_dead_letter_by_stale_owner(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, attempts=5, status="sent")
        self._set_delivery(delivery, claim_token=None)
        policy = self._policy(jitter_fn=lambda: 0)
        decision = policy.apply_failure(
            tenant_id=tenant_id, delivery_id=delivery.id, now=FIXED_NOW,
            error_code="delivery_claim_mismatch", retryable=False, max_attempts=5,
            expected_claim_token="tok-stale", allowed_current_statuses={"processing", "failed"},
        )
        self.assertEqual(decision.action, "stale_owner")
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "sent")

    def test_delivered_is_never_downgraded_to_failed_by_stale_owner(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, attempts=1, status="delivered")
        self._set_delivery(delivery, claim_token=None)
        policy = self._policy(jitter_fn=lambda: 0)
        decision = policy.apply_failure(
            tenant_id=tenant_id, delivery_id=delivery.id, now=FIXED_NOW,
            error_code="whatsapp_provider_send_failed", retryable=True, max_attempts=5,
            expected_claim_token="tok-stale", allowed_current_statuses={"processing", "failed"},
        )
        self.assertEqual(decision.action, "stale_owner")
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "delivered")

    def test_read_is_never_degraded_by_stale_owner(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, attempts=1, status="read")
        self._set_delivery(delivery, claim_token=None)
        policy = self._policy(jitter_fn=lambda: 0)
        decision = policy.apply_failure(
            tenant_id=tenant_id, delivery_id=delivery.id, now=FIXED_NOW,
            error_code="whatsapp_provider_send_failed", retryable=True, max_attempts=5,
            expected_claim_token="tok-stale", allowed_current_statuses={"processing", "failed"},
        )
        self.assertEqual(decision.action, "stale_owner")
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "read")

    def test_manual_review_is_never_degraded_by_stale_owner(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, attempts=1, status="manual_review")
        self._set_delivery(delivery, claim_token=None)
        policy = self._policy(jitter_fn=lambda: 0)
        decision = policy.apply_failure(
            tenant_id=tenant_id, delivery_id=delivery.id, now=FIXED_NOW,
            error_code="whatsapp_provider_send_failed", retryable=True, max_attempts=5,
            expected_claim_token="tok-stale", allowed_current_statuses={"processing", "failed"},
        )
        self.assertEqual(decision.action, "stale_owner")
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "manual_review")

    def test_status_outside_allowed_set_is_treated_as_stale(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, attempts=1, status="pending")
        self._set_delivery(delivery, claim_token="tok-current")
        policy = self._policy(jitter_fn=lambda: 0)
        decision = policy.apply_failure(
            tenant_id=tenant_id, delivery_id=delivery.id, now=FIXED_NOW,
            error_code="whatsapp_provider_send_failed", retryable=True, max_attempts=5,
            expected_claim_token="tok-current", allowed_current_statuses={"processing", "failed"},
        )
        self.assertEqual(decision.action, "stale_owner")

    def test_commit_false_does_not_commit_but_still_mutates_session(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, attempts=1, status="processing")
        policy = self._policy(jitter_fn=lambda: 0)
        policy.apply_failure(
            tenant_id=tenant_id, delivery_id=delivery.id, now=FIXED_NOW,
            error_code="whatsapp_provider_send_failed", retryable=True, max_attempts=5,
            commit=False,
        )
        self.assertEqual(delivery.status, "failed")
        self.db.commit()
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "failed")


if __name__ == "__main__":
    unittest.main()
