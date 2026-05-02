import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
import unittest

from fastapi import HTTPException

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
TEST_DB_PATH = Path("serviai_sprint2_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.analytics import Agent, Call, CallEvent, MetricSnapshotDaily
from app.models.identity import Tenant
from app.services.call_persistence_service import (
    CallPersistenceService,
    PersistCallInput,
    PersistEventInput,
)
from app.services.call_status_normalizer import CallStatusNormalizer


class Sprint2AnalyticsPersistenceTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        TEST_DB_PATH.unlink(missing_ok=True)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

    def tearDown(self):
        Base.metadata.drop_all(bind=engine)

    def seed_tenant(self) -> Tenant:
        with SessionLocal() as db:
            tenant = Tenant(name="Empresa Demo", slug="empresa-demo")
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            return tenant

    def test_agent_is_created_per_tenant(self):
        tenant = self.seed_tenant()

        with SessionLocal() as db:
            agent = Agent(
                tenant_id=tenant.id,
                external_provider="ultravox",
                external_agent_id="provider-agent-1",
                name="Agente Ventas",
                channel_type="voice",
                status="active",
            )
            db.add(agent)
            db.commit()
            db.refresh(agent)

            persisted = db.get(Agent, agent.id)
            self.assertEqual(persisted.tenant_id, tenant.id)
            self.assertEqual(persisted.external_agent_id, "provider-agent-1")

    def test_call_can_be_created_with_tenant_and_agent(self):
        tenant = self.seed_tenant()
        started_at = datetime(2026, 5, 2, 14, 0, tzinfo=UTC)

        with SessionLocal() as db:
            agent = Agent(tenant_id=tenant.id, name="Agente Soporte")
            db.add(agent)
            db.commit()
            db.refresh(agent)

            call = CallPersistenceService(db).persist_call(
                PersistCallInput(
                    tenant_id=tenant.id,
                    external_provider="ultravox",
                    external_call_id="call-001",
                    agent_id=agent.id,
                    provider_agent_id="provider-agent-1",
                    provider_status="completed",
                    started_at=started_at,
                    duration_seconds=185,
                    billed_minutes=Decimal("4.00"),
                    summary="Cliente solicita informacion comercial.",
                    short_summary="Solicitud comercial",
                    direction="outbound",
                    customer_phone="+573001112233",
                    last_synced_at=started_at,
                )
            )

            self.assertEqual(call.tenant_id, tenant.id)
            self.assertEqual(call.agent_id, agent.id)
            self.assertEqual(call.provider_status, "completed")
            self.assertEqual(call.normalized_status, "answered")
            self.assertEqual(call.duration_seconds, 185)
            self.assertEqual(call.billed_minutes, Decimal("4.00"))

    def test_call_can_be_created_without_agent(self):
        tenant = self.seed_tenant()

        with SessionLocal() as db:
            call = CallPersistenceService(db).persist_call(
                PersistCallInput(
                    tenant_id=tenant.id,
                    external_provider="ultravox",
                    external_call_id="call-no-agent",
                    provider_status="missed",
                    started_at=datetime(2026, 5, 2, 15, 0, tzinfo=UTC),
                )
            )

            self.assertIsNone(call.agent_id)
            self.assertEqual(call.normalized_status, "unanswered")

    def test_call_requires_tenant(self):
        with SessionLocal() as db:
            with self.assertRaises(ValueError):
                CallPersistenceService(db).persist_call(
                    PersistCallInput(
                        tenant_id="",
                        external_provider="ultravox",
                        external_call_id="call-without-tenant",
                        provider_status="completed",
                        started_at=datetime(2026, 5, 2, 15, 0, tzinfo=UTC),
                    )
                )

    def test_call_rejects_agent_from_another_tenant(self):
        first_tenant = self.seed_tenant()
        with SessionLocal() as db:
            second_tenant = Tenant(name="Otro Tenant", slug="otro-tenant")
            db.add(second_tenant)
            db.commit()
            db.refresh(second_tenant)
            foreign_agent = Agent(tenant_id=second_tenant.id, name="Agente Externo")
            db.add(foreign_agent)
            db.commit()
            db.refresh(foreign_agent)

            with self.assertRaises(HTTPException):
                CallPersistenceService(db).persist_call(
                    PersistCallInput(
                        tenant_id=first_tenant.id,
                        external_provider="ultravox",
                        external_call_id="call-foreign-agent",
                        agent_id=foreign_agent.id,
                        provider_status="completed",
                        started_at=datetime(2026, 5, 2, 15, 0, tzinfo=UTC),
                    )
                )

    def test_call_event_is_associated_to_call_and_tenant(self):
        tenant = self.seed_tenant()

        with SessionLocal() as db:
            service = CallPersistenceService(db)
            call = service.persist_call(
                PersistCallInput(
                    tenant_id=tenant.id,
                    external_provider="ultravox",
                    external_call_id="call-event-001",
                    provider_status="started",
                    started_at=datetime(2026, 5, 2, 16, 0, tzinfo=UTC),
                )
            )

            event = service.persist_event(
                PersistEventInput(
                    tenant_id=tenant.id,
                    call_id=call.id,
                    event_type="call.started",
                    provider_event_id="evt-001",
                    payload_json={"status": "started", "callId": "call-event-001"},
                )
            )

            persisted_event = db.get(CallEvent, event.id)
            self.assertEqual(persisted_event.call_id, call.id)
            self.assertEqual(persisted_event.tenant_id, tenant.id)
            self.assertEqual(persisted_event.payload_json["status"], "started")

    def test_metric_snapshot_daily_supports_future_analytics_queries(self):
        tenant = self.seed_tenant()

        with SessionLocal() as db:
            snapshot = MetricSnapshotDaily(
                tenant_id=tenant.id,
                date=datetime(2026, 5, 2, tzinfo=UTC).date(),
                calls_total=3,
                calls_answered=2,
                calls_unanswered=1,
                duration_total_seconds=420,
                billed_minutes=Decimal("8.00"),
            )
            db.add(snapshot)
            db.commit()
            db.refresh(snapshot)

            self.assertEqual(snapshot.tenant_id, tenant.id)
            self.assertIsNone(snapshot.agent_id)
            self.assertEqual(snapshot.calls_total, 3)
            self.assertEqual(snapshot.billed_minutes, Decimal("8.00"))

    def test_status_normalizer_supports_required_statuses(self):
        normalizer = CallStatusNormalizer()

        self.assertEqual(normalizer.normalize("ringing"), "in_progress")
        self.assertEqual(normalizer.normalize("completed"), "answered")
        self.assertEqual(normalizer.normalize("missed"), "unanswered")
        self.assertEqual(normalizer.normalize("declined"), "rejected")
        self.assertEqual(normalizer.normalize("failure"), "failed")
        self.assertEqual(normalizer.normalize("canceled"), "cancelled")
        self.assertEqual(normalizer.normalize("human_transfer"), "transferred")
        self.assertEqual(normalizer.normalize("voicemail"), "voicemail")

    def test_existing_call_is_updated_by_provider_identity(self):
        tenant = self.seed_tenant()

        with SessionLocal() as db:
            service = CallPersistenceService(db)
            first = service.persist_call(
                PersistCallInput(
                    tenant_id=tenant.id,
                    external_provider="ultravox",
                    external_call_id="call-upsert-001",
                    provider_status="started",
                    started_at=datetime(2026, 5, 2, 17, 0, tzinfo=UTC),
                )
            )
            second = service.persist_call(
                PersistCallInput(
                    tenant_id=tenant.id,
                    external_provider="ultravox",
                    external_call_id="call-upsert-001",
                    provider_status="completed",
                    started_at=datetime(2026, 5, 2, 17, 0, tzinfo=UTC),
                    duration_seconds=90,
                    billed_minutes="2.00",
                )
            )

            self.assertEqual(first.id, second.id)
            self.assertEqual(db.query(Call).count(), 1)
            self.assertEqual(second.normalized_status, "answered")
            self.assertEqual(second.duration_seconds, 90)


if __name__ == "__main__":
    unittest.main()
