import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

TEST_DB_PATH = Path("serviai_notification_delivery_recovery_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.crm import CrmWhatsAppMessage
from app.models.identity import Tenant
from app.models.notifications import DomainEvent, NotificationDelivery, TenantNotificationRule
from app.services.notification_delivery_recovery_service import NotificationDeliveryRecoveryService
from app.services.notification_retry_policy import NotificationRetryPolicy

FIXED_NOW = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)


class _BaseRecoveryTestCase(unittest.TestCase):
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
        self.retry_policy = NotificationRetryPolicy(
            self.db, base_retry_seconds=30, max_retry_seconds=3600, jitter_seconds=0, jitter_fn=lambda: 0
        )
        self.service = NotificationDeliveryRecoveryService(self.db, retry_policy=self.retry_policy)

    def tearDown(self):
        self.db.close()

    def _create_tenant(self, slug: str = "recovery-tenant") -> str:
        tenant = Tenant(name=f"Empresa {slug}", slug=f"{slug}-{uuid4().hex[:8]}")
        self.db.add(tenant)
        self.db.commit()
        self.db.refresh(tenant)
        return tenant.id

    def _create_processing_delivery(
        self,
        tenant_id: str,
        *,
        claim_expires_at: datetime | None,
        updated_at_override: datetime | None = None,
        attempts: int = 1,
        metadata_json: dict | None = None,
    ) -> NotificationDelivery:
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
            status="processing",
            scheduled_for=FIXED_NOW - timedelta(hours=1),
            attempts=attempts,
            idempotency_key=f"delivery-{uuid4().hex[:8]}",
            metadata_json=metadata_json or {},
            claim_token="tok-abc",
            claimed_at=FIXED_NOW - timedelta(minutes=5),
            claim_expires_at=claim_expires_at,
        )
        self.db.add(delivery)
        self.db.commit()
        self.db.refresh(delivery)
        if updated_at_override is not None:
            self.db.query(NotificationDelivery).filter(NotificationDelivery.id == delivery.id).update(
                {"updated_at": updated_at_override}
            )
            self.db.commit()
            self.db.refresh(delivery)
        return delivery

    def _create_message(
        self,
        tenant_id: str,
        delivery: NotificationDelivery | None,
        *,
        status: str,
        provider_message_id: str | None = None,
        link_via_metadata_only: bool = False,
    ) -> CrmWhatsAppMessage:
        message = CrmWhatsAppMessage(
            tenant_id=tenant_id,
            provider="whatsapp_cloud",
            provider_message_id=provider_message_id,
            direction="outbound",
            to_phone="+573001112233",
            status=status,
            metadata_json={},
            notification_delivery_id=None if (delivery is None or link_via_metadata_only) else delivery.id,
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        if delivery is not None and link_via_metadata_only:
            metadata = dict(delivery.metadata_json or {})
            metadata["crm_whatsapp_message_id"] = message.id
            delivery.metadata_json = metadata
            self.db.add(delivery)
            self.db.commit()
        return message


class RecoverySelectionTests(_BaseRecoveryTestCase):
    def test_active_claim_is_not_recovered(self):
        tenant_id = self._create_tenant()
        self._create_processing_delivery(tenant_id, claim_expires_at=FIXED_NOW + timedelta(minutes=5))
        outcomes = self.service.recover_batch(now=FIXED_NOW, legacy_stale_seconds=300, max_attempts=5, batch_size=50)
        self.assertEqual(outcomes, [])

    def test_expired_lease_is_recovered(self):
        tenant_id = self._create_tenant()
        delivery = self._create_processing_delivery(tenant_id, claim_expires_at=FIXED_NOW - timedelta(seconds=1))
        outcomes = self.service.recover_batch(now=FIXED_NOW, legacy_stale_seconds=300, max_attempts=5, batch_size=50)
        self.assertEqual([o.delivery_id for o in outcomes], [delivery.id])

    def test_legacy_processing_recent_is_not_recovered(self):
        tenant_id = self._create_tenant()
        self._create_processing_delivery(
            tenant_id, claim_expires_at=None, updated_at_override=FIXED_NOW - timedelta(seconds=10)
        )
        outcomes = self.service.recover_batch(now=FIXED_NOW, legacy_stale_seconds=300, max_attempts=5, batch_size=50)
        self.assertEqual(outcomes, [])

    def test_legacy_processing_old_is_recovered(self):
        tenant_id = self._create_tenant()
        delivery = self._create_processing_delivery(
            tenant_id, claim_expires_at=None, updated_at_override=FIXED_NOW - timedelta(seconds=600)
        )
        outcomes = self.service.recover_batch(now=FIXED_NOW, legacy_stale_seconds=300, max_attempts=5, batch_size=50)
        self.assertEqual([o.delivery_id for o in outcomes], [delivery.id])

    def test_batch_size_is_respected(self):
        tenant_id = self._create_tenant()
        for _ in range(5):
            self._create_processing_delivery(tenant_id, claim_expires_at=FIXED_NOW - timedelta(seconds=1))
        outcomes = self.service.recover_batch(now=FIXED_NOW, legacy_stale_seconds=300, max_attempts=5, batch_size=2)
        self.assertEqual(len(outcomes), 2)

    def test_now_must_be_timezone_aware(self):
        with self.assertRaises(ValueError):
            self.service.recover_batch(
                now=datetime(2026, 8, 1, 10, 0, 0), legacy_stale_seconds=300, max_attempts=5, batch_size=50
            )


class RecoveryReconciliationTests(_BaseRecoveryTestCase):
    def test_sent_message_syncs_delivery(self):
        tenant_id = self._create_tenant()
        delivery = self._create_processing_delivery(tenant_id, claim_expires_at=FIXED_NOW - timedelta(seconds=1))
        self._create_message(tenant_id, delivery, status="sent", provider_message_id="wamid.1")
        outcomes = self.service.recover_batch(now=FIXED_NOW, legacy_stale_seconds=300, max_attempts=5, batch_size=50)
        self.assertEqual(outcomes[0].action, "sent")
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "sent")
        self.assertEqual(delivery.provider_message_id, "wamid.1")

    def test_delivered_message_syncs_delivery(self):
        tenant_id = self._create_tenant()
        delivery = self._create_processing_delivery(tenant_id, claim_expires_at=FIXED_NOW - timedelta(seconds=1))
        self._create_message(tenant_id, delivery, status="delivered", provider_message_id="wamid.2")
        outcomes = self.service.recover_batch(now=FIXED_NOW, legacy_stale_seconds=300, max_attempts=5, batch_size=50)
        self.assertEqual(outcomes[0].action, "delivered")
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "delivered")

    def test_read_message_syncs_delivery(self):
        tenant_id = self._create_tenant()
        delivery = self._create_processing_delivery(tenant_id, claim_expires_at=FIXED_NOW - timedelta(seconds=1))
        self._create_message(tenant_id, delivery, status="read", provider_message_id="wamid.3")
        outcomes = self.service.recover_batch(now=FIXED_NOW, legacy_stale_seconds=300, max_attempts=5, batch_size=50)
        self.assertEqual(outcomes[0].action, "read")
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "read")
        self.assertIsNotNone(delivery.read_at)

    def test_queued_with_provider_id_is_treated_as_sent(self):
        tenant_id = self._create_tenant()
        delivery = self._create_processing_delivery(tenant_id, claim_expires_at=FIXED_NOW - timedelta(seconds=1))
        self._create_message(tenant_id, delivery, status="queued", provider_message_id="wamid.4")
        outcomes = self.service.recover_batch(now=FIXED_NOW, legacy_stale_seconds=300, max_attempts=5, batch_size=50)
        self.assertEqual(outcomes[0].action, "sent")
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "sent")

    def test_queued_without_provider_id_is_manual_review(self):
        tenant_id = self._create_tenant()
        delivery = self._create_processing_delivery(tenant_id, claim_expires_at=FIXED_NOW - timedelta(seconds=1))
        self._create_message(tenant_id, delivery, status="queued", provider_message_id=None)
        outcomes = self.service.recover_batch(now=FIXED_NOW, legacy_stale_seconds=300, max_attempts=5, batch_size=50)
        self.assertEqual(outcomes[0].action, "manual_review")
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "manual_review")
        self.assertEqual(delivery.error_message, "whatsapp_send_outcome_unknown")

    def test_failed_message_triggers_retry(self):
        tenant_id = self._create_tenant()
        delivery = self._create_processing_delivery(tenant_id, claim_expires_at=FIXED_NOW - timedelta(seconds=1), attempts=1)
        self._create_message(tenant_id, delivery, status="failed")
        outcomes = self.service.recover_batch(now=FIXED_NOW, legacy_stale_seconds=300, max_attempts=5, batch_size=50)
        self.assertEqual(outcomes[0].action, "retry")
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "failed")
        self.assertIsNotNone(delivery.next_attempt_at)

    def test_failed_message_exhausted_produces_dead_letter(self):
        tenant_id = self._create_tenant()
        delivery = self._create_processing_delivery(tenant_id, claim_expires_at=FIXED_NOW - timedelta(seconds=1), attempts=5)
        self._create_message(tenant_id, delivery, status="failed")
        outcomes = self.service.recover_batch(now=FIXED_NOW, legacy_stale_seconds=300, max_attempts=5, batch_size=50)
        self.assertEqual(outcomes[0].action, "dead_letter")
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "dead_letter")

    def test_no_message_triggers_retry(self):
        tenant_id = self._create_tenant()
        delivery = self._create_processing_delivery(tenant_id, claim_expires_at=FIXED_NOW - timedelta(seconds=1))
        outcomes = self.service.recover_batch(now=FIXED_NOW, legacy_stale_seconds=300, max_attempts=5, batch_size=50)
        self.assertEqual(outcomes[0].action, "retry")
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "failed")
        self.assertEqual(delivery.error_message, "worker_claim_expired_before_send")

    def test_recovery_never_calls_a_provider_client(self):
        # NotificationDeliveryRecoveryService has no client dependency at all —
        # this test documents that guarantee by construction.
        self.assertFalse(hasattr(self.service, "client"))
        self.assertFalse(hasattr(self.service, "_client"))

    def test_claim_fields_are_cleared_after_recovery(self):
        tenant_id = self._create_tenant()
        delivery = self._create_processing_delivery(tenant_id, claim_expires_at=FIXED_NOW - timedelta(seconds=1))
        self._create_message(tenant_id, delivery, status="sent", provider_message_id="wamid.5")
        self.service.recover_batch(now=FIXED_NOW, legacy_stale_seconds=300, max_attempts=5, batch_size=50)
        self.db.refresh(delivery)
        self.assertIsNone(delivery.claim_token)
        self.assertIsNone(delivery.claimed_at)
        self.assertIsNone(delivery.claim_expires_at)

    def test_claim_fields_are_cleared_for_manual_review(self):
        tenant_id = self._create_tenant()
        delivery = self._create_processing_delivery(tenant_id, claim_expires_at=FIXED_NOW - timedelta(seconds=1))
        self._create_message(tenant_id, delivery, status="queued", provider_message_id=None)
        self.service.recover_batch(now=FIXED_NOW, legacy_stale_seconds=300, max_attempts=5, batch_size=50)
        self.db.refresh(delivery)
        self.assertIsNone(delivery.claim_token)

    def test_respects_tenant_scoping(self):
        tenant_a = self._create_tenant("a")
        tenant_b = self._create_tenant("b")
        delivery_a = self._create_processing_delivery(tenant_a, claim_expires_at=FIXED_NOW - timedelta(seconds=1))
        delivery_b = self._create_processing_delivery(tenant_b, claim_expires_at=FIXED_NOW + timedelta(minutes=5))
        outcomes = self.service.recover_batch(now=FIXED_NOW, legacy_stale_seconds=300, max_attempts=5, batch_size=50)
        self.assertEqual([o.delivery_id for o in outcomes], [delivery_a.id])
        self.db.refresh(delivery_b)
        self.assertEqual(delivery_b.status, "processing")

    def test_message_from_other_tenant_is_ignored(self):
        tenant_a = self._create_tenant("a")
        tenant_b = self._create_tenant("b")
        delivery = self._create_processing_delivery(tenant_a, claim_expires_at=FIXED_NOW - timedelta(seconds=1))
        # A message with the same delivery id string but a different tenant must never match.
        other_message = CrmWhatsAppMessage(
            tenant_id=tenant_b,
            provider="whatsapp_cloud",
            provider_message_id="wamid.cross-tenant",
            direction="outbound",
            to_phone="+573001112233",
            status="sent",
            metadata_json={},
            notification_delivery_id=delivery.id,
        )
        self.db.add(other_message)
        self.db.commit()
        outcomes = self.service.recover_batch(now=FIXED_NOW, legacy_stale_seconds=300, max_attempts=5, batch_size=50)
        self.assertEqual(outcomes[0].action, "retry")
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "failed")

    def test_fallback_via_metadata_crm_whatsapp_message_id_works(self):
        tenant_id = self._create_tenant()
        delivery = self._create_processing_delivery(tenant_id, claim_expires_at=FIXED_NOW - timedelta(seconds=1))
        self._create_message(
            tenant_id, delivery, status="delivered", provider_message_id="wamid.6", link_via_metadata_only=True
        )
        outcomes = self.service.recover_batch(now=FIXED_NOW, legacy_stale_seconds=300, max_attempts=5, batch_size=50)
        self.assertEqual(outcomes[0].action, "delivered")

    def test_read_status_is_never_degraded_by_recovery(self):
        tenant_id = self._create_tenant()
        delivery = self._create_processing_delivery(tenant_id, claim_expires_at=FIXED_NOW - timedelta(seconds=1))
        self._create_message(tenant_id, delivery, status="read", provider_message_id="wamid.7")
        self.service.recover_batch(now=FIXED_NOW, legacy_stale_seconds=300, max_attempts=5, batch_size=50)
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "read")

    def test_provider_message_id_is_copied_to_delivery(self):
        tenant_id = self._create_tenant()
        delivery = self._create_processing_delivery(tenant_id, claim_expires_at=FIXED_NOW - timedelta(seconds=1))
        self._create_message(tenant_id, delivery, status="sent", provider_message_id="wamid.copy-me")
        self.service.recover_batch(now=FIXED_NOW, legacy_stale_seconds=300, max_attempts=5, batch_size=50)
        self.db.refresh(delivery)
        self.assertEqual(delivery.provider_message_id, "wamid.copy-me")

    def test_timestamps_are_filled_safely_when_missing(self):
        tenant_id = self._create_tenant()
        delivery = self._create_processing_delivery(tenant_id, claim_expires_at=FIXED_NOW - timedelta(seconds=1))
        self._create_message(tenant_id, delivery, status="delivered", provider_message_id="wamid.8")
        self.service.recover_batch(now=FIXED_NOW, legacy_stale_seconds=300, max_attempts=5, batch_size=50)
        self.db.refresh(delivery)
        self.assertIsNotNone(delivery.sent_at)
        self.assertIsNotNone(delivery.delivered_at)


if __name__ == "__main__":
    unittest.main()
