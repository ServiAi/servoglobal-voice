import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

TEST_DB_PATH = Path("serviai_notification_delivery_claim_service_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from sqlalchemy.dialects import postgresql

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.identity import Tenant
from app.models.notifications import DomainEvent, NotificationDelivery, TenantNotificationRule
from app.services.notification_delivery_claim_service import (
    NotificationDeliveryClaim,
    NotificationDeliveryClaimService,
)

FIXED_NOW = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
PAST = FIXED_NOW - timedelta(hours=1)
FUTURE = FIXED_NOW + timedelta(hours=1)


class _BaseClaimTestCase(unittest.TestCase):
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
        self.service = NotificationDeliveryClaimService(self.db)

    def tearDown(self):
        self.db.close()

    def _create_tenant(self, slug: str = "claim-tenant") -> str:
        tenant = Tenant(name=f"Empresa {slug}", slug=f"{slug}-{uuid4().hex[:8]}")
        self.db.add(tenant)
        self.db.commit()
        self.db.refresh(tenant)
        return tenant.id

    def _create_delivery(
        self,
        tenant_id: str,
        *,
        status: str = "pending",
        scheduled_for: datetime = PAST,
        next_attempt_at: datetime | None = None,
        attempts: int = 0,
        channel: str = "whatsapp",
        created_offset: int = 0,
    ) -> NotificationDelivery:
        event = DomainEvent(
            tenant_id=tenant_id,
            event_type="booking.created",
            source="test",
            idempotency_key=f"evt-{uuid4().hex[:8]}",
            payload_json={},
            available_at=PAST,
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
            channel=channel,
            recipient="+573001112233",
            status=status,
            scheduled_for=scheduled_for,
            next_attempt_at=next_attempt_at,
            attempts=attempts,
            idempotency_key=f"delivery-{uuid4().hex[:8]}",
            metadata_json={},
        )
        self.db.add(delivery)
        self.db.commit()
        self.db.refresh(delivery)
        if created_offset:
            delivery.created_at = delivery.created_at + timedelta(seconds=created_offset)
            self.db.add(delivery)
            self.db.commit()
            self.db.refresh(delivery)
        return delivery


class ClaimBatchEligibilityTests(_BaseClaimTestCase):
    def test_pending_due_is_claimed(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, status="pending", scheduled_for=PAST)
        claims = self.service.claim_batch(now=FIXED_NOW, lease_seconds=120, max_attempts=5, batch_size=10)
        self.assertEqual([c.delivery_id for c in claims], [delivery.id])

    def test_pending_future_is_not_claimed(self):
        tenant_id = self._create_tenant()
        self._create_delivery(tenant_id, status="pending", scheduled_for=FUTURE)
        claims = self.service.claim_batch(now=FIXED_NOW, lease_seconds=120, max_attempts=5, batch_size=10)
        self.assertEqual(claims, [])

    def test_failed_due_is_claimed(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, status="failed", scheduled_for=PAST)
        claims = self.service.claim_batch(now=FIXED_NOW, lease_seconds=120, max_attempts=5, batch_size=10)
        self.assertEqual([c.delivery_id for c in claims], [delivery.id])

    def test_failed_with_future_next_attempt_is_not_claimed(self):
        tenant_id = self._create_tenant()
        self._create_delivery(tenant_id, status="failed", scheduled_for=PAST, next_attempt_at=FUTURE)
        claims = self.service.claim_batch(now=FIXED_NOW, lease_seconds=120, max_attempts=5, batch_size=10)
        self.assertEqual(claims, [])

    def test_processing_is_not_claimed(self):
        tenant_id = self._create_tenant()
        self._create_delivery(tenant_id, status="processing", scheduled_for=PAST)
        claims = self.service.claim_batch(now=FIXED_NOW, lease_seconds=120, max_attempts=5, batch_size=10)
        self.assertEqual(claims, [])

    def test_sent_is_not_claimed(self):
        tenant_id = self._create_tenant()
        self._create_delivery(tenant_id, status="sent", scheduled_for=PAST)
        claims = self.service.claim_batch(now=FIXED_NOW, lease_seconds=120, max_attempts=5, batch_size=10)
        self.assertEqual(claims, [])

    def test_delivered_is_not_claimed(self):
        tenant_id = self._create_tenant()
        self._create_delivery(tenant_id, status="delivered", scheduled_for=PAST)
        claims = self.service.claim_batch(now=FIXED_NOW, lease_seconds=120, max_attempts=5, batch_size=10)
        self.assertEqual(claims, [])

    def test_read_is_not_claimed(self):
        tenant_id = self._create_tenant()
        self._create_delivery(tenant_id, status="read", scheduled_for=PAST)
        claims = self.service.claim_batch(now=FIXED_NOW, lease_seconds=120, max_attempts=5, batch_size=10)
        self.assertEqual(claims, [])

    def test_skipped_is_not_claimed(self):
        tenant_id = self._create_tenant()
        self._create_delivery(tenant_id, status="skipped", scheduled_for=PAST)
        claims = self.service.claim_batch(now=FIXED_NOW, lease_seconds=120, max_attempts=5, batch_size=10)
        self.assertEqual(claims, [])

    def test_cancelled_is_not_claimed(self):
        tenant_id = self._create_tenant()
        self._create_delivery(tenant_id, status="cancelled", scheduled_for=PAST)
        claims = self.service.claim_batch(now=FIXED_NOW, lease_seconds=120, max_attempts=5, batch_size=10)
        self.assertEqual(claims, [])

    def test_dead_letter_is_not_claimed(self):
        tenant_id = self._create_tenant()
        self._create_delivery(tenant_id, status="dead_letter", scheduled_for=PAST)
        claims = self.service.claim_batch(now=FIXED_NOW, lease_seconds=120, max_attempts=5, batch_size=10)
        self.assertEqual(claims, [])

    def test_manual_review_is_not_claimed(self):
        tenant_id = self._create_tenant()
        self._create_delivery(tenant_id, status="manual_review", scheduled_for=PAST)
        claims = self.service.claim_batch(now=FIXED_NOW, lease_seconds=120, max_attempts=5, batch_size=10)
        self.assertEqual(claims, [])

    def test_non_whatsapp_channel_is_not_claimed(self):
        tenant_id = self._create_tenant()
        self._create_delivery(tenant_id, status="pending", scheduled_for=PAST, channel="email")
        claims = self.service.claim_batch(now=FIXED_NOW, lease_seconds=120, max_attempts=5, batch_size=10)
        self.assertEqual(claims, [])

    def test_attempts_at_max_is_not_claimed(self):
        tenant_id = self._create_tenant()
        self._create_delivery(tenant_id, status="failed", scheduled_for=PAST, attempts=5)
        claims = self.service.claim_batch(now=FIXED_NOW, lease_seconds=120, max_attempts=5, batch_size=10)
        self.assertEqual(claims, [])

    def test_batch_size_is_respected(self):
        tenant_id = self._create_tenant()
        for _ in range(5):
            self._create_delivery(tenant_id, status="pending", scheduled_for=PAST)
        claims = self.service.claim_batch(now=FIXED_NOW, lease_seconds=120, max_attempts=5, batch_size=2)
        self.assertEqual(len(claims), 2)

    def test_order_by_next_due_first(self):
        tenant_id = self._create_tenant()
        later = self._create_delivery(tenant_id, status="pending", scheduled_for=PAST + timedelta(minutes=5))
        earlier = self._create_delivery(tenant_id, status="pending", scheduled_for=PAST)
        claims = self.service.claim_batch(now=FIXED_NOW, lease_seconds=120, max_attempts=5, batch_size=10)
        self.assertEqual([c.delivery_id for c in claims], [earlier.id, later.id])

    def test_naive_now_is_rejected(self):
        tenant_id = self._create_tenant()
        self._create_delivery(tenant_id, status="pending", scheduled_for=PAST)
        with self.assertRaises(ValueError):
            self.service.claim_batch(
                now=datetime(2026, 8, 1, 10, 0, 0), lease_seconds=120, max_attempts=5, batch_size=10
            )


class ClaimBatchApplicationTests(_BaseClaimTestCase):
    def test_attempts_increments_once(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, status="pending", scheduled_for=PAST)
        self.service.claim_batch(now=FIXED_NOW, lease_seconds=120, max_attempts=5, batch_size=10)
        self.db.refresh(delivery)
        self.assertEqual(delivery.attempts, 1)

    def test_status_becomes_processing(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, status="pending", scheduled_for=PAST)
        self.service.claim_batch(now=FIXED_NOW, lease_seconds=120, max_attempts=5, batch_size=10)
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "processing")

    def test_claim_token_is_not_empty(self):
        tenant_id = self._create_tenant()
        self._create_delivery(tenant_id, status="pending", scheduled_for=PAST)
        claims = self.service.claim_batch(now=FIXED_NOW, lease_seconds=120, max_attempts=5, batch_size=10)
        self.assertTrue(claims[0].claim_token)

    def test_claim_tokens_are_unique(self):
        tenant_id = self._create_tenant()
        for _ in range(3):
            self._create_delivery(tenant_id, status="pending", scheduled_for=PAST)
        claims = self.service.claim_batch(now=FIXED_NOW, lease_seconds=120, max_attempts=5, batch_size=10)
        tokens = {c.claim_token for c in claims}
        self.assertEqual(len(tokens), 3)

    def test_claimed_at_matches_now(self):
        tenant_id = self._create_tenant()
        self._create_delivery(tenant_id, status="pending", scheduled_for=PAST)
        claims = self.service.claim_batch(now=FIXED_NOW, lease_seconds=120, max_attempts=5, batch_size=10)
        self.assertEqual(claims[0].claimed_at, FIXED_NOW)

    def test_claim_expires_at_matches_lease(self):
        tenant_id = self._create_tenant()
        self._create_delivery(tenant_id, status="pending", scheduled_for=PAST)
        claims = self.service.claim_batch(now=FIXED_NOW, lease_seconds=120, max_attempts=5, batch_size=10)
        self.assertEqual(claims[0].claim_expires_at, FIXED_NOW + timedelta(seconds=120))

    def test_next_attempt_at_is_protected_until_lease_expires(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, status="pending", scheduled_for=PAST)
        self.service.claim_batch(now=FIXED_NOW, lease_seconds=120, max_attempts=5, batch_size=10)
        self.db.refresh(delivery)
        stored = delivery.next_attempt_at
        if stored.tzinfo is None:
            stored = stored.replace(tzinfo=timezone.utc)
        self.assertEqual(stored, FIXED_NOW + timedelta(seconds=120))

    def test_claim_one_claims_eligible_delivery(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, status="pending", scheduled_for=PAST)
        claim = self.service.claim_one(
            tenant_id=tenant_id, delivery_id=delivery.id, now=FIXED_NOW, lease_seconds=120, max_attempts=5
        )
        self.assertIsInstance(claim, NotificationDeliveryClaim)
        self.assertEqual(claim.delivery_id, delivery.id)

    def test_second_claim_one_loses(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, status="pending", scheduled_for=PAST)
        first = self.service.claim_one(
            tenant_id=tenant_id, delivery_id=delivery.id, now=FIXED_NOW, lease_seconds=120, max_attempts=5
        )
        second = self.service.claim_one(
            tenant_id=tenant_id, delivery_id=delivery.id, now=FIXED_NOW, lease_seconds=120, max_attempts=5
        )
        self.assertIsNotNone(first)
        self.assertIsNone(second)

    def test_claim_one_wrong_tenant_does_not_claim(self):
        tenant_id = self._create_tenant("owner")
        other_tenant_id = self._create_tenant("other")
        delivery = self._create_delivery(tenant_id, status="pending", scheduled_for=PAST)
        claim = self.service.claim_one(
            tenant_id=other_tenant_id, delivery_id=delivery.id, now=FIXED_NOW, lease_seconds=120, max_attempts=5
        )
        self.assertIsNone(claim)
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "pending")

    def test_claim_one_naive_now_rejected(self):
        tenant_id = self._create_tenant()
        delivery = self._create_delivery(tenant_id, status="pending", scheduled_for=PAST)
        with self.assertRaises(ValueError):
            self.service.claim_one(
                tenant_id=tenant_id,
                delivery_id=delivery.id,
                now=datetime(2026, 8, 1, 10, 0, 0),
                lease_seconds=120,
                max_attempts=5,
            )

    def test_claim_does_not_touch_other_deliveries(self):
        tenant_id = self._create_tenant()
        claimed = self._create_delivery(tenant_id, status="pending", scheduled_for=PAST)
        untouched = self._create_delivery(tenant_id, status="pending", scheduled_for=FUTURE)
        self.service.claim_one(
            tenant_id=tenant_id, delivery_id=claimed.id, now=FIXED_NOW, lease_seconds=120, max_attempts=5
        )
        self.db.refresh(untouched)
        self.assertEqual(untouched.status, "pending")
        self.assertEqual(untouched.attempts, 0)


class PostgresqlCompilationTests(_BaseClaimTestCase):
    def test_batch_select_compiles_with_for_update_skip_locked_on_postgresql(self):
        query = self.service.build_batch_select(now=FIXED_NOW, max_attempts=5, batch_size=10)
        compiled = str(query.compile(dialect=postgresql.dialect()))
        self.assertIn("FOR UPDATE SKIP LOCKED", compiled)


if __name__ == "__main__":
    unittest.main()
