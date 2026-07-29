"""Real PostgreSQL concurrency tests for the durable notification claim service.

These tests are skipped unless NOTIFICATION_TEST_DATABASE_URL points to a
dedicated local PostgreSQL database. They never touch staging/production and
never send real WhatsApp messages -- they only exercise
`SELECT ... FOR UPDATE SKIP LOCKED` claim semantics with genuine concurrent
sessions.

Run with a local docker-compose Postgres:

    docker compose up -d postgres
    docker exec serviai_postgres createdb -U serviai serviai_notification_worker_test

    cd backend
    ULTRAVOX_API_KEY=test \
    NOTIFICATION_TEST_DATABASE_URL="postgresql+psycopg://serviai:serviai@localhost:5432/serviai_notification_worker_test" \
    python -m unittest test_notification_worker_postgres -v
"""

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

NOTIFICATION_TEST_DATABASE_URL = os.environ.get("NOTIFICATION_TEST_DATABASE_URL")

if NOTIFICATION_TEST_DATABASE_URL:
    os.environ.setdefault("ULTRAVOX_API_KEY", "test")
    os.environ["DATABASE_URL"] = NOTIFICATION_TEST_DATABASE_URL

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.crm import CrmWhatsAppMessage
from app.models.identity import Tenant
from app.models.notifications import DomainEvent, NotificationDelivery, TenantNotificationRule
from app.services.notification_delivery_claim_service import NotificationDeliveryClaimService
from app.services.notification_delivery_recovery_service import NotificationDeliveryRecoveryService
from app.services.notification_retry_policy import NotificationRetryPolicy
from app.services.whatsapp_message_service import WhatsAppSendResult
from app.services.whatsapp_notification_executor import WhatsAppNotificationExecutor

FIXED_NOW = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
PAST = FIXED_NOW - timedelta(hours=1)


@unittest.skipUnless(
    NOTIFICATION_TEST_DATABASE_URL,
    "NOTIFICATION_TEST_DATABASE_URL not set; skipping real PostgreSQL concurrency tests",
)
class NotificationWorkerPostgresConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(NOTIFICATION_TEST_DATABASE_URL, pool_pre_ping=True)
        if cls.engine.dialect.name != "postgresql":
            raise unittest.SkipTest("NOTIFICATION_TEST_DATABASE_URL must point to a PostgreSQL database")
        Base.metadata.create_all(bind=cls.engine)
        cls.SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self):
        self.db = self.SessionLocal()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def _create_tenant(self, session, slug: str) -> str:
        tenant = Tenant(name=f"Empresa {slug}", slug=f"{slug}-{uuid4().hex[:8]}")
        session.add(tenant)
        session.commit()
        session.refresh(tenant)
        return tenant.id

    def _seed_deliveries(self, session, tenant_id: str, count: int) -> list[str]:
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
        session.add_all([event, rule])
        session.commit()
        session.refresh(event)
        session.refresh(rule)
        ids = []
        for _ in range(count):
            delivery = NotificationDelivery(
                tenant_id=tenant_id,
                domain_event_id=event.id,
                notification_rule_id=rule.id,
                channel="whatsapp",
                recipient="+573001112233",
                status="pending",
                scheduled_for=PAST,
                attempts=0,
                idempotency_key=f"delivery-{uuid4().hex[:8]}",
                metadata_json={},
            )
            session.add(delivery)
            session.commit()
            session.refresh(delivery)
            ids.append(delivery.id)
        return ids

    def _claim_worker(self, *, batch_size: int) -> list[str]:
        session = self.SessionLocal()
        try:
            claims = NotificationDeliveryClaimService(session).claim_batch(
                now=FIXED_NOW, lease_seconds=120, max_attempts=5, batch_size=batch_size
            )
            return [c.delivery_id for c in claims]
        finally:
            session.close()

    def test_two_workers_never_claim_the_same_id(self):
        tenant_id = self._create_tenant(self.db, "concurrency-a")
        ids = set(self._seed_deliveries(self.db, tenant_id, 20))

        with ThreadPoolExecutor(max_workers=2) as pool:
            future_a = pool.submit(self._claim_worker, batch_size=10)
            future_b = pool.submit(self._claim_worker, batch_size=10)
            claimed_a = future_a.result()
            claimed_b = future_b.result()

        self.assertEqual(set(claimed_a) & set(claimed_b), set())
        self.assertEqual(set(claimed_a) | set(claimed_b), ids)
        self.assertEqual(len(claimed_a), 10)
        self.assertEqual(len(claimed_b), 10)

    def test_three_workers_do_not_claim_duplicates(self):
        tenant_id = self._create_tenant(self.db, "concurrency-b")
        ids = set(self._seed_deliveries(self.db, tenant_id, 30))

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(self._claim_worker, batch_size=10) for _ in range(3)]
            results = [f.result() for f in futures]

        all_claimed = [item for sub in results for item in sub]
        self.assertEqual(len(all_claimed), len(set(all_claimed)))
        self.assertEqual(set(all_claimed), ids)

    def test_claimed_sum_matches_seeded_deliveries(self):
        tenant_id = self._create_tenant(self.db, "concurrency-c")
        ids = set(self._seed_deliveries(self.db, tenant_id, 15))
        claimed = self._claim_worker(batch_size=100)
        self.assertEqual(set(claimed), ids)

    def test_rollback_releases_locks_for_another_worker(self):
        tenant_id = self._create_tenant(self.db, "concurrency-d")
        ids = self._seed_deliveries(self.db, tenant_id, 1)

        session_a = self.SessionLocal()
        query = NotificationDeliveryClaimService(session_a).build_batch_select(
            now=FIXED_NOW, max_attempts=5, batch_size=10
        )
        session_a.execute(query).scalars().all()  # acquire the row lock, never commit the claim
        session_a.rollback()
        session_a.close()

        claimed = self._claim_worker(batch_size=10)
        self.assertEqual(claimed, ids)

    def test_batch_concurrency_preserves_single_attempt_increment(self):
        tenant_id = self._create_tenant(self.db, "concurrency-e")
        ids = set(self._seed_deliveries(self.db, tenant_id, 8))

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self._claim_worker, batch_size=4) for _ in range(2)]
            results = [f.result() for f in futures]

        all_claimed = [item for sub in results for item in sub]
        self.assertEqual(set(all_claimed), ids)

        verify = self.SessionLocal()
        try:
            rows = verify.query(NotificationDelivery).filter(NotificationDelivery.id.in_(ids)).all()
            for row in rows:
                self.assertEqual(row.status, "processing")
                self.assertEqual(row.attempts, 1)
        finally:
            verify.close()


@unittest.skipUnless(
    NOTIFICATION_TEST_DATABASE_URL,
    "NOTIFICATION_TEST_DATABASE_URL not set; skipping real PostgreSQL concurrency tests",
)
class NotificationRecoveryPostgresConcurrencyTests(unittest.TestCase):
    """Real concurrency coverage for the Phase 6 stabilization fixes:
    recovery's single-commit batch and the retry policy's stale-owner guard,
    exercised against genuine concurrent PostgreSQL sessions instead of
    sqlite (which cannot demonstrate row-level locking races)."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(NOTIFICATION_TEST_DATABASE_URL, pool_pre_ping=True)
        if cls.engine.dialect.name != "postgresql":
            raise unittest.SkipTest("NOTIFICATION_TEST_DATABASE_URL must point to a PostgreSQL database")
        Base.metadata.create_all(bind=cls.engine)
        cls.SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self):
        self.db = self.SessionLocal()

    def tearDown(self):
        self.db.rollback()
        self.db.close()
        # recover_batch() has no tenant filter by design (recovery must sweep
        # every tenant's abandoned claims) -- so a row left over from one
        # test would otherwise leak into the next test's global batch query.
        cleanup = self.SessionLocal()
        try:
            cleanup.query(NotificationDelivery).delete()
            cleanup.query(TenantNotificationRule).delete()
            cleanup.query(DomainEvent).delete()
            cleanup.query(Tenant).delete()
            cleanup.commit()
        finally:
            cleanup.close()

    def _create_tenant(self, session, slug: str) -> str:
        tenant = Tenant(name=f"Empresa {slug}", slug=f"{slug}-{uuid4().hex[:8]}")
        session.add(tenant)
        session.commit()
        session.refresh(tenant)
        return tenant.id

    def _seed_processing_deliveries(self, session, tenant_id: str, count: int) -> list[str]:
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
        session.add_all([event, rule])
        session.commit()
        session.refresh(event)
        session.refresh(rule)
        ids = []
        for _ in range(count):
            delivery = NotificationDelivery(
                tenant_id=tenant_id,
                domain_event_id=event.id,
                notification_rule_id=rule.id,
                channel="whatsapp",
                recipient="+573001112233",
                status="processing",
                scheduled_for=PAST,
                attempts=1,
                idempotency_key=f"delivery-{uuid4().hex[:8]}",
                metadata_json={},
                claim_token=f"tok-{uuid4().hex[:8]}",
                claimed_at=PAST,
                claim_expires_at=PAST,
            )
            session.add(delivery)
            session.commit()
            session.refresh(delivery)
            ids.append(delivery.id)
        return ids

    def _recovery_worker(self, *, batch_size: int) -> list[str]:
        session = self.SessionLocal()
        try:
            policy = NotificationRetryPolicy(
                session, base_retry_seconds=30, max_retry_seconds=3600, jitter_seconds=0, jitter_fn=lambda: 0
            )
            service = NotificationDeliveryRecoveryService(session, retry_policy=policy)
            outcomes = service.recover_batch(
                now=FIXED_NOW, legacy_stale_seconds=300, max_attempts=5, batch_size=batch_size
            )
            return [o.delivery_id for o in outcomes]
        finally:
            session.close()

    def test_two_concurrent_recoveries_never_process_the_same_row(self):
        tenant_id = self._create_tenant(self.db, "recovery-concurrency-a")
        ids = set(self._seed_processing_deliveries(self.db, tenant_id, 20))

        with ThreadPoolExecutor(max_workers=2) as pool:
            future_a = pool.submit(self._recovery_worker, batch_size=10)
            future_b = pool.submit(self._recovery_worker, batch_size=10)
            recovered_a = future_a.result()
            recovered_b = future_b.result()

        self.assertEqual(set(recovered_a) & set(recovered_b), set())
        self.assertEqual(set(recovered_a) | set(recovered_b), ids)

    def test_recovered_total_matches_seeded_total(self):
        tenant_id = self._create_tenant(self.db, "recovery-concurrency-b")
        ids = set(self._seed_processing_deliveries(self.db, tenant_id, 15))
        recovered = self._recovery_worker(batch_size=100)
        self.assertEqual(set(recovered), ids)

    def test_old_claim_token_never_overwrites_a_newer_one(self):
        tenant_id = self._create_tenant(self.db, "stale-owner-c")
        delivery_id = self._seed_processing_deliveries(self.db, tenant_id, 1)[0]

        # Simulate a fresh claim replacing the token this (stale) caller held.
        setup = self.SessionLocal()
        try:
            delivery = setup.query(NotificationDelivery).filter(NotificationDelivery.id == delivery_id).one()
            delivery.claim_token = "tok-new-real-owner"
            setup.add(delivery)
            setup.commit()
        finally:
            setup.close()

        session = self.SessionLocal()
        try:
            policy = NotificationRetryPolicy(
                session, base_retry_seconds=30, max_retry_seconds=3600, jitter_seconds=0, jitter_fn=lambda: 0
            )
            decision = policy.apply_failure(
                tenant_id=tenant_id,
                delivery_id=delivery_id,
                now=FIXED_NOW,
                error_code="whatsapp_provider_send_failed",
                retryable=True,
                max_attempts=5,
                expected_claim_token="tok-stale-old-owner",
                allowed_current_statuses={"processing", "failed"},
            )
        finally:
            session.close()
        self.assertEqual(decision.action, "stale_owner")

        verify = self.SessionLocal()
        try:
            row = verify.query(NotificationDelivery).filter(NotificationDelivery.id == delivery_id).one()
            self.assertEqual(row.claim_token, "tok-new-real-owner")
        finally:
            verify.close()

    def test_stale_owner_never_degrades_a_sent_delivery(self):
        tenant_id = self._create_tenant(self.db, "stale-owner-d")
        delivery_id = self._seed_processing_deliveries(self.db, tenant_id, 1)[0]

        setup = self.SessionLocal()
        try:
            delivery = setup.query(NotificationDelivery).filter(NotificationDelivery.id == delivery_id).one()
            delivery.status = "sent"
            delivery.claim_token = None
            setup.add(delivery)
            setup.commit()
        finally:
            setup.close()

        session = self.SessionLocal()
        try:
            policy = NotificationRetryPolicy(
                session, base_retry_seconds=30, max_retry_seconds=3600, jitter_seconds=0, jitter_fn=lambda: 0
            )
            decision = policy.apply_failure(
                tenant_id=tenant_id,
                delivery_id=delivery_id,
                now=FIXED_NOW,
                error_code="delivery_claim_mismatch",
                retryable=False,
                max_attempts=5,
                expected_claim_token="tok-stale",
                allowed_current_statuses={"processing", "failed"},
            )
        finally:
            session.close()
        self.assertEqual(decision.action, "stale_owner")

        verify = self.SessionLocal()
        try:
            row = verify.query(NotificationDelivery).filter(NotificationDelivery.id == delivery_id).one()
            self.assertEqual(row.status, "sent")
        finally:
            verify.close()

    def test_recovery_and_finalization_race_leaves_a_valid_terminal_state(self):
        # One real thread runs recovery on an expired-lease delivery while
        # another concurrently finalizes it as "sent" (simulating an HTTP
        # send that succeeded right as the lease expired). Whichever session
        # wins the row lock first, the delivery must end on a coherent
        # terminal state -- never left stuck in "processing".
        tenant_id = self._create_tenant(self.db, "race-e")
        delivery_id = self._seed_processing_deliveries(self.db, tenant_id, 1)[0]

        def finalize_as_sent():
            session = self.SessionLocal()
            try:
                delivery = (
                    session.query(NotificationDelivery)
                    .filter(NotificationDelivery.id == delivery_id)
                    .with_for_update()
                    .one()
                )
                delivery.status = "sent"
                delivery.provider_message_id = "wamid.race"
                delivery.sent_at = FIXED_NOW
                delivery.claim_token = None
                delivery.claimed_at = None
                delivery.claim_expires_at = None
                delivery.next_attempt_at = None
                delivery.error_message = None
                session.add(delivery)
                session.commit()
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            future_recovery = pool.submit(self._recovery_worker, batch_size=10)
            future_finalize = pool.submit(finalize_as_sent)
            future_recovery.result()
            future_finalize.result()

        verify = self.SessionLocal()
        try:
            row = verify.query(NotificationDelivery).filter(NotificationDelivery.id == delivery_id).one()
            self.assertIn(row.status, {"sent", "failed", "dead_letter", "manual_review"})
            self.assertNotEqual(row.status, "processing")
        finally:
            verify.close()


@unittest.skipUnless(
    NOTIFICATION_TEST_DATABASE_URL,
    "NOTIFICATION_TEST_DATABASE_URL not set; skipping real PostgreSQL concurrency tests",
)
class WhatsAppFinalizationPostgresConcurrencyTests(unittest.TestCase):
    """Real concurrency coverage for the atomic post-Meta finalization fix
    (preserve notification claim through finalization): the executor's
    FOR UPDATE finalize helpers, exercised with genuine concurrent
    PostgreSQL sessions and fake WhatsAppSendResult objects -- no real
    WhatsApp/Meta call is ever made."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(NOTIFICATION_TEST_DATABASE_URL, pool_pre_ping=True)
        if cls.engine.dialect.name != "postgresql":
            raise unittest.SkipTest("NOTIFICATION_TEST_DATABASE_URL must point to a PostgreSQL database")
        Base.metadata.create_all(bind=cls.engine)
        cls.SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self):
        self.db = self.SessionLocal()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def _create_tenant(self, session, slug: str) -> str:
        tenant = Tenant(name=f"Empresa {slug}", slug=f"{slug}-{uuid4().hex[:8]}")
        session.add(tenant)
        session.commit()
        session.refresh(tenant)
        return tenant.id

    def _seed_claimed_delivery(
        self, session, tenant_id: str, *, claim_token: str, status: str = "processing"
    ) -> str:
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
        session.add_all([event, rule])
        session.commit()
        session.refresh(event)
        session.refresh(rule)
        delivery = NotificationDelivery(
            tenant_id=tenant_id,
            domain_event_id=event.id,
            notification_rule_id=rule.id,
            channel="whatsapp",
            recipient="+573001112233",
            status=status,
            scheduled_for=PAST,
            attempts=1,
            idempotency_key=f"delivery-{uuid4().hex[:8]}",
            metadata_json={},
            claim_token=claim_token,
            claimed_at=PAST,
            claim_expires_at=FIXED_NOW + timedelta(minutes=5),
        )
        session.add(delivery)
        session.commit()
        session.refresh(delivery)
        return delivery.id

    def test_two_finalizers_do_not_both_write_the_same_delivery(self):
        tenant_id = self._create_tenant(self.db, "finalize-race-a")
        delivery_id = self._seed_claimed_delivery(self.db, tenant_id, claim_token="tok-new-owner")

        # Both messages exist up front so only the FOR UPDATE finalize step
        # itself races -- not message creation.
        setup = self.SessionLocal()
        try:
            stale_message = CrmWhatsAppMessage(
                tenant_id=tenant_id,
                notification_delivery_id=delivery_id,
                direction="outbound",
                to_phone="+573001112233",
                status="sent",
                provider_message_id="wamid.stale",
                metadata_json={},
                sent_at=FIXED_NOW,
            )
            current_message = CrmWhatsAppMessage(
                tenant_id=tenant_id,
                notification_delivery_id=delivery_id,
                direction="outbound",
                to_phone="+573001112233",
                status="sent",
                provider_message_id="wamid.current",
                metadata_json={},
                sent_at=FIXED_NOW,
            )
            setup.add_all([stale_message, current_message])
            setup.commit()
            setup.refresh(stale_message)
            setup.refresh(current_message)
            stale_message_id, current_message_id = stale_message.id, current_message.id
        finally:
            setup.close()

        def finalize(*, claim_token: str, message_id: str, provider_message_id: str) -> str:
            session = self.SessionLocal()
            try:
                message = session.query(CrmWhatsAppMessage).filter(CrmWhatsAppMessage.id == message_id).one()
                result = WhatsAppSendResult(status="sent", message=message, provider_message_id=provider_message_id)
                executor = WhatsAppNotificationExecutor(session, client=object())
                outcome = executor._finalize_after_send(
                    tenant_id=tenant_id,
                    delivery_id=delivery_id,
                    claim_token=claim_token,
                    current_time=FIXED_NOW,
                    result=result,
                )
                return outcome.outcome
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            future_stale = pool.submit(
                finalize, claim_token="tok-stale-owner", message_id=stale_message_id, provider_message_id="wamid.stale"
            )
            future_current = pool.submit(
                finalize, claim_token="tok-new-owner", message_id=current_message_id, provider_message_id="wamid.current"
            )
            outcome_stale = future_stale.result()
            outcome_current = future_current.result()

        # Regardless of which thread's FOR UPDATE wins the row lock first,
        # exactly one of them performs the actual write (either by owning
        # the claim directly, or by reconciling from evidence); the other
        # must find nothing left to do.
        writers = [o for o in (outcome_stale, outcome_current) if o in ("sent", "stale_claim_reconciled")]
        ignored = [o for o in (outcome_stale, outcome_current) if o == "stale_claim_ignored"]
        self.assertEqual(len(writers), 1)
        self.assertEqual(len(ignored), 1)

        verify = self.SessionLocal()
        try:
            row = verify.query(NotificationDelivery).filter(NotificationDelivery.id == delivery_id).one()
            self.assertEqual(row.status, "sent")
            self.assertIn(row.provider_message_id, ("wamid.stale", "wamid.current"))
            # Whichever thread actually wrote: if it owned the claim
            # (claim_token matched), the claim is cleared; if it wrote via
            # stale-claim reconciliation (its own token did NOT match), the
            # claim is intentionally left untouched -- reconciliation must
            # never invent, corrupt, or steal a claim_token it doesn't own.
            self.assertIn(row.claim_token, (None, "tok-new-owner"))
        finally:
            verify.close()

    def test_old_token_never_overwrites_a_newer_token_during_finalization(self):
        tenant_id = self._create_tenant(self.db, "finalize-race-b")
        delivery_id = self._seed_claimed_delivery(self.db, tenant_id, claim_token="tok-new-owner")

        session = self.SessionLocal()
        try:
            result = WhatsAppSendResult(status="failed", message=None, error_message="whatsapp_send_failed")
            executor = WhatsAppNotificationExecutor(session, client=object())
            outcome = executor._finalize_after_send(
                tenant_id=tenant_id,
                delivery_id=delivery_id,
                claim_token="tok-stale-owner",
                current_time=FIXED_NOW,
                result=result,
            )
        finally:
            session.close()

        self.assertEqual(outcome.outcome, "stale_claim_ignored")
        verify = self.SessionLocal()
        try:
            row = verify.query(NotificationDelivery).filter(NotificationDelivery.id == delivery_id).one()
            self.assertEqual(row.claim_token, "tok-new-owner")
            self.assertEqual(row.status, "processing")
        finally:
            verify.close()

    def test_provider_failure_applies_real_backoff_after_finalize_leaves_it_untouched(self):
        tenant_id = self._create_tenant(self.db, "backoff-real")
        delivery_id = self._seed_claimed_delivery(self.db, tenant_id, claim_token="tok-a")

        session = self.SessionLocal()
        try:
            result = WhatsAppSendResult(status="failed", message=None, error_message="whatsapp_send_failed")
            executor = WhatsAppNotificationExecutor(session, client=object())
            outcome = executor._finalize_after_send(
                tenant_id=tenant_id,
                delivery_id=delivery_id,
                claim_token="tok-a",
                current_time=FIXED_NOW,
                result=result,
            )
            self.assertEqual(outcome.outcome, "failed")
            self.assertTrue(outcome.retryable)

            # The executor must not have finalized anything yet.
            row = session.query(NotificationDelivery).filter(NotificationDelivery.id == delivery_id).one()
            self.assertEqual(row.status, "processing")
            self.assertEqual(row.claim_token, "tok-a")

            policy = NotificationRetryPolicy(
                session, base_retry_seconds=30, max_retry_seconds=3600, jitter_seconds=0, jitter_fn=lambda: 0
            )
            decision = policy.apply_failure(
                tenant_id=tenant_id,
                delivery_id=delivery_id,
                now=FIXED_NOW,
                error_code="whatsapp_provider_send_failed",
                retryable=True,
                max_attempts=5,
                expected_claim_token="tok-a",
                allowed_current_statuses={"processing", "failed"},
            )
            self.assertEqual(decision.action, "retry")
        finally:
            session.close()

        verify = self.SessionLocal()
        try:
            row = verify.query(NotificationDelivery).filter(NotificationDelivery.id == delivery_id).one()
            self.assertEqual(row.status, "failed")
            self.assertIsNone(row.claim_token)
            self.assertIsNotNone(row.next_attempt_at)
            stored = row.next_attempt_at
            if stored.tzinfo is None:
                stored = stored.replace(tzinfo=timezone.utc)
            self.assertEqual(stored, FIXED_NOW + timedelta(seconds=30))
        finally:
            verify.close()

    def test_missing_provider_id_finalize_does_not_erase_a_newer_claim(self):
        tenant_id = self._create_tenant(self.db, "manual-review-race")
        delivery_id = self._seed_claimed_delivery(self.db, tenant_id, claim_token="tok-new-owner")

        session = self.SessionLocal()
        try:
            result = WhatsAppSendResult(
                status="manual_review", message=None, error_message="whatsapp_provider_message_id_missing"
            )
            executor = WhatsAppNotificationExecutor(session, client=object())
            outcome = executor._finalize_manual_review(
                tenant_id=tenant_id, delivery_id=delivery_id, claim_token="tok-stale-owner", result=result
            )
        finally:
            session.close()

        self.assertEqual(outcome.outcome, "stale_claim_ignored")
        verify = self.SessionLocal()
        try:
            row = verify.query(NotificationDelivery).filter(NotificationDelivery.id == delivery_id).one()
            self.assertEqual(row.claim_token, "tok-new-owner")
            self.assertEqual(row.status, "processing")
            self.assertIsNone(row.error_message)
        finally:
            verify.close()

    def test_finalize_and_recovery_race_leaves_a_coherent_sent_state(self):
        # The lease is already expired, so recovery is eligible to reclaim
        # this delivery at the exact same time the original (slow) executor
        # is finally getting around to finalizing its successful send.
        tenant_id = self._create_tenant(self.db, "finalize-recovery-race")
        delivery_id = self._seed_claimed_delivery(self.db, tenant_id, claim_token="tok-race")

        setup = self.SessionLocal()
        try:
            row = setup.query(NotificationDelivery).filter(NotificationDelivery.id == delivery_id).one()
            row.claim_expires_at = FIXED_NOW - timedelta(seconds=1)
            setup.add(row)
            setup.commit()
        finally:
            setup.close()

        def finalize_via_executor() -> str:
            session = self.SessionLocal()
            try:
                message = CrmWhatsAppMessage(
                    tenant_id=tenant_id,
                    notification_delivery_id=delivery_id,
                    direction="outbound",
                    to_phone="+573001112233",
                    status="sent",
                    provider_message_id="wamid.finalize-race",
                    metadata_json={},
                    sent_at=FIXED_NOW,
                )
                session.add(message)
                session.commit()
                session.refresh(message)
                result = WhatsAppSendResult(status="sent", message=message, provider_message_id="wamid.finalize-race")
                executor = WhatsAppNotificationExecutor(session, client=object())
                outcome = executor._finalize_after_send(
                    tenant_id=tenant_id,
                    delivery_id=delivery_id,
                    claim_token="tok-race",
                    current_time=FIXED_NOW,
                    result=result,
                )
                return outcome.outcome
            finally:
                session.close()

        def run_recovery() -> list[str]:
            session = self.SessionLocal()
            try:
                policy = NotificationRetryPolicy(
                    session, base_retry_seconds=30, max_retry_seconds=3600, jitter_seconds=0, jitter_fn=lambda: 0
                )
                service = NotificationDeliveryRecoveryService(session, retry_policy=policy)
                outcomes = service.recover_batch(
                    now=FIXED_NOW, legacy_stale_seconds=300, max_attempts=5, batch_size=10
                )
                return [o.delivery_id for o in outcomes]
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            future_finalize = pool.submit(finalize_via_executor)
            future_recovery = pool.submit(run_recovery)
            future_finalize.result()
            future_recovery.result()

        verify = self.SessionLocal()
        try:
            row = verify.query(NotificationDelivery).filter(NotificationDelivery.id == delivery_id).one()
            # Whichever side wins the row lock first, the CrmWhatsAppMessage
            # evidence created by finalize_via_executor is always the only
            # evidence in existence, so the delivery must always converge
            # on "sent" -- never left processing, never dead-lettered.
            self.assertEqual(row.status, "sent")
            self.assertEqual(row.provider_message_id, "wamid.finalize-race")
            self.assertIsNone(row.claim_token)
        finally:
            verify.close()


if __name__ == "__main__":
    unittest.main()
