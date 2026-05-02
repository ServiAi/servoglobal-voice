import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
import unittest

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
os.environ["ULTRAVOX_WEBHOOK_SECRET"] = "test-webhook-secret"
TEST_DB_PATH = Path("serviai_sprint3_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.analytics import Agent, Call, CallEvent
from app.models.identity import Tenant
from app.services.ultravox_ingestion_service import UltravoxIngestionService


class Sprint3UltravoxIngestionTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        TEST_DB_PATH.unlink(missing_ok=True)

    def setUp(self):
        settings.ULTRAVOX_WEBHOOK_SECRET = "test-webhook-secret"
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        app.dependency_overrides.clear()
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def seed_tenant_and_agent(self) -> tuple[Tenant, Agent]:
        with SessionLocal() as db:
            tenant = Tenant(name="Empresa Demo", slug="empresa-demo")
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            agent = Agent(
                tenant_id=tenant.id,
                external_provider="ultravox",
                external_agent_id="agent-upstream-1",
                name="Agente Ventas",
            )
            db.add(agent)
            db.commit()
            db.refresh(agent)
            return tenant, agent

    def test_webhook_persists_upstream_event_and_initial_call(self):
        tenant, agent = self.seed_tenant_and_agent()

        response = self.client.post(
            "/api/v1/integrations/ultravox/events",
            headers={"x-serviai-webhook-secret": "test-webhook-secret"},
            json={
                "eventType": "call.started",
                "eventId": "evt-started-1",
                "callId": "uvx-call-1",
                "tenant_id": tenant.id,
                "agentId": agent.external_agent_id,
                "status": "started",
                "startedAt": "2026-05-02T14:00:00Z",
                "direction": "outbound",
                "customerPhone": "+573001112233",
            },
        )

        self.assertEqual(response.status_code, 200)
        with SessionLocal() as db:
            call = db.query(Call).filter_by(external_call_id="uvx-call-1").one()
            event = db.query(CallEvent).filter_by(provider_event_id="evt-started-1").one()
            self.assertEqual(call.tenant_id, tenant.id)
            self.assertEqual(call.agent_id, agent.id)
            self.assertEqual(call.provider_status, "started")
            self.assertEqual(call.normalized_status, "in_progress")
            self.assertEqual(event.call_id, call.id)

    def test_call_progressively_updates_joined_ended_summary_and_billing(self):
        tenant, agent = self.seed_tenant_and_agent()

        with SessionLocal() as db:
            service = UltravoxIngestionService(db)
            service.ingest_event(
                {
                    "eventType": "call.started",
                    "eventId": "evt-1",
                    "callId": "uvx-progressive",
                    "tenant_id": tenant.id,
                    "agentId": agent.external_agent_id,
                    "status": "started",
                    "startedAt": "2026-05-02T14:00:00Z",
                }
            )
            service.ingest_event(
                {
                    "eventType": "call.joined",
                    "eventId": "evt-2",
                    "callId": "uvx-progressive",
                    "tenant_id": tenant.id,
                    "status": "joined",
                    "joinedAt": "2026-05-02T14:00:12Z",
                }
            )
            service.ingest_event(
                {
                    "eventType": "call.ended",
                    "eventId": "evt-3",
                    "callId": "uvx-progressive",
                    "tenant_id": tenant.id,
                    "status": "ended",
                    "endedAt": "2026-05-02T14:03:20Z",
                    "durationSeconds": 200,
                }
            )
            service.ingest_event(
                {
                    "eventType": "call.summary.completed",
                    "eventId": "evt-4",
                    "callId": "uvx-progressive",
                    "tenant_id": tenant.id,
                    "summary": "Cliente pidio una demo comercial.",
                    "shortSummary": "Demo comercial",
                }
            )
            service.ingest_event(
                {
                    "eventType": "call.billing.updated",
                    "eventId": "evt-5",
                    "callId": "uvx-progressive",
                    "tenant_id": tenant.id,
                    "billedMinutes": "4.00",
                }
            )

            call = db.query(Call).filter_by(external_call_id="uvx-progressive").one()
            self.assertEqual(db.query(Call).count(), 1)
            self.assertEqual(db.query(CallEvent).count(), 5)
            self.assertEqual(call.agent_id, agent.id)
            self.assertEqual(call.provider_status, "ended")
            self.assertEqual(call.normalized_status, "answered")
            self.assertEqual(call.duration_seconds, 200)
            self.assertEqual(call.billed_minutes, Decimal("4.00"))
            self.assertEqual(call.summary, "Cliente pidio una demo comercial.")
            self.assertEqual(call.short_summary, "Demo comercial")
            self.assertIsNotNone(call.last_synced_at)

    def test_late_reconciliation_completes_missing_data_without_event(self):
        tenant, _ = self.seed_tenant_and_agent()

        with SessionLocal() as db:
            service = UltravoxIngestionService(db)
            service.ingest_event(
                {
                    "eventType": "call.started",
                    "eventId": "evt-reconcile-1",
                    "callId": "uvx-reconcile",
                    "tenant_id": tenant.id,
                    "status": "started",
                    "startedAt": "2026-05-02T15:00:00Z",
                }
            )

            result = service.reconcile_call(
                {
                    "callId": "uvx-reconcile",
                    "tenant_id": tenant.id,
                    "status": "completed",
                    "endedAt": "2026-05-02T15:02:00Z",
                    "durationSeconds": 120,
                    "billedMinutes": 2,
                    "summary": "Datos completados por reconciliacion.",
                }
            )

            self.assertIsNone(result.event)
            self.assertEqual(db.query(CallEvent).count(), 1)
            self.assertEqual(result.call.normalized_status, "answered")
            self.assertEqual(result.call.duration_seconds, 120)
            self.assertEqual(result.call.billed_minutes, Decimal("2.00"))
            self.assertEqual(result.call.summary, "Datos completados por reconciliacion.")

    def test_missing_agent_mapping_keeps_call_unassigned(self):
        tenant, _ = self.seed_tenant_and_agent()

        with SessionLocal() as db:
            result = UltravoxIngestionService(db).ingest_event(
                {
                    "eventType": "call.started",
                    "eventId": "evt-unassigned",
                    "callId": "uvx-unassigned",
                    "tenant_id": tenant.id,
                    "agentId": "unknown-agent",
                    "status": "started",
                    "startedAt": "2026-05-02T16:00:00Z",
                }
            )

            self.assertIsNone(result.call.agent_id)
            self.assertEqual(result.call.provider_agent_id, "unknown-agent")

    def test_webhook_rejects_invalid_secret(self):
        tenant, _ = self.seed_tenant_and_agent()

        response = self.client.post(
            "/api/v1/integrations/ultravox/events",
            headers={"x-serviai-webhook-secret": "wrong"},
            json={
                "eventType": "call.started",
                "callId": "uvx-secret",
                "tenant_id": tenant.id,
                "status": "started",
            },
        )

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
