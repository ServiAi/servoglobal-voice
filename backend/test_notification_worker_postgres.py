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
from app.models.identity import Tenant
from app.models.notifications import DomainEvent, NotificationDelivery, TenantNotificationRule
from app.services.notification_delivery_claim_service import NotificationDeliveryClaimService

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


if __name__ == "__main__":
    unittest.main()
