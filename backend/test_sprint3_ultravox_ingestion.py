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

    def official_payload(
        self,
        event: str,
        call_id: str,
        tenant: Tenant | None = None,
        agent_external_id: str | None = None,
        metadata: dict | None = None,
        **call_overrides,
    ) -> dict:
        call_metadata = metadata.copy() if metadata is not None else {}
        if tenant is not None and not call_metadata:
            call_metadata = {
                "tenant_id": tenant.id,
                "tenant_slug": tenant.slug,
                "direction": "outbound",
                "customer_phone": "+573001112233",
            }
        call = {
            "callId": call_id,
            "created": "2026-05-02T14:00:00Z",
            "joined": None,
            "ended": None,
            "shortSummary": None,
            "summary": None,
            "metadata": call_metadata,
            "endReason": None,
            "billingStatus": "BILLING_STATUS_PENDING",
            "agent": {"agentId": agent_external_id} if agent_external_id else {},
        }
        call.update(call_overrides)
        return {"event": event, "call": call}

    def test_webhook_persists_official_started_event_and_initial_call(self):
        tenant, agent = self.seed_tenant_and_agent()

        response = self.client.post(
            "/api/v1/integrations/ultravox/events",
            headers={"x-serviai-webhook-secret": "test-webhook-secret"},
            json=self.official_payload(
                "call.started",
                "uvx-call-1",
                tenant,
                agent.external_agent_id,
            ),
        )

        self.assertEqual(response.status_code, 200)
        with SessionLocal() as db:
            call = db.query(Call).filter_by(external_call_id="uvx-call-1").one()
            event = db.query(CallEvent).filter_by(event_type="call.started").one()
            self.assertEqual(call.tenant_id, tenant.id)
            self.assertEqual(call.agent_id, agent.id)
            self.assertEqual(call.provider_status, "started")
            self.assertEqual(call.normalized_status, "in_progress")
            self.assertEqual(call.direction, "outbound")
            self.assertEqual(call.customer_phone, "+573001112233")
            self.assertEqual(event.call_id, call.id)
            self.assertEqual(event.payload_json["call"]["callId"], "uvx-call-1")

    def test_official_events_progressively_update_joined_ended_summary_and_billing(self):
        tenant, agent = self.seed_tenant_and_agent()

        with SessionLocal() as db:
            service = UltravoxIngestionService(db)
            started = service.ingest_event(
                self.official_payload(
                    "call.started",
                    "uvx-progressive",
                    tenant,
                    agent.external_agent_id,
                )
            )
            self.assertEqual(started.call.normalized_status, "in_progress")

            joined = service.ingest_event(
                self.official_payload(
                    "call.joined",
                    "uvx-progressive",
                    tenant,
                    agent.external_agent_id,
                    joined="2026-05-02T14:00:12Z",
                )
            )
            self.assertEqual(joined.call.normalized_status, "in_progress")
            self.assertIsNotNone(joined.call.joined_at)

            ended = service.ingest_event(
                self.official_payload(
                    "call.ended",
                    "uvx-progressive",
                    tenant,
                    agent.external_agent_id,
                    joined="2026-05-02T14:00:12Z",
                    ended="2026-05-02T14:03:20Z",
                    endReason="hangup",
                )
            )
            self.assertEqual(ended.call.normalized_status, "answered")
            self.assertEqual(ended.call.duration_seconds, 188)

            billed = service.ingest_event(
                self.official_payload(
                    "call.billed",
                    "uvx-progressive",
                    tenant,
                    agent.external_agent_id,
                    joined="2026-05-02T14:00:12Z",
                    ended="2026-05-02T14:03:20Z",
                    endReason="hangup",
                    billingStatus="BILLING_STATUS_BILLED",
                    billedDuration="240s",
                    summary="Cliente pidio una demo comercial.",
                    shortSummary="Demo comercial",
                )
            )

            call = db.query(Call).filter_by(external_call_id="uvx-progressive").one()
            self.assertEqual(db.query(Call).count(), 1)
            self.assertEqual(db.query(CallEvent).count(), 4)
            self.assertEqual(call.agent_id, agent.id)
            self.assertEqual(call.provider_status, "BILLING_STATUS_BILLED")
            self.assertEqual(call.normalized_status, "answered")
            self.assertEqual(billed.call.normalized_status, "answered")
            self.assertEqual(call.duration_seconds, 188)
            self.assertEqual(call.billed_minutes, Decimal("4.00"))
            self.assertEqual(call.summary, "Cliente pidio una demo comercial.")
            self.assertEqual(call.short_summary, "Demo comercial")
            self.assertIsNotNone(call.last_synced_at)

    def test_official_reconciliation_completes_missing_data_without_event(self):
        tenant, _ = self.seed_tenant_and_agent()

        with SessionLocal() as db:
            service = UltravoxIngestionService(db)
            service.ingest_event(
                self.official_payload("call.started", "uvx-reconcile", tenant)
            )

            result = service.reconcile_call(
                self.official_payload(
                    "call.billed",
                    "uvx-reconcile",
                    metadata={"tenant_slug": tenant.slug},
                    joined="2026-05-02T15:00:15Z",
                    ended="2026-05-02T15:02:00Z",
                    endReason="agent_hangup",
                    billingStatus="BILLING_STATUS_BILLED",
                    billedDuration="120s",
                    summary="Datos completados por reconciliacion.",
                )
            )

            self.assertIsNone(result.event)
            self.assertEqual(db.query(CallEvent).count(), 1)
            self.assertEqual(result.call.normalized_status, "answered")
            self.assertEqual(result.call.duration_seconds, 105)
            self.assertEqual(result.call.billed_minutes, Decimal("2.00"))
            self.assertEqual(result.call.summary, "Datos completados por reconciliacion.")

    def test_official_tenant_slug_and_missing_agent_mapping_keeps_call_unassigned(self):
        tenant, _ = self.seed_tenant_and_agent()

        with SessionLocal() as db:
            result = UltravoxIngestionService(db).ingest_event(
                self.official_payload(
                    "call.started",
                    "uvx-unassigned",
                    metadata={"tenant_slug": tenant.slug},
                    agent_external_id="unknown-agent",
                )
            )

            self.assertIsNone(result.call.agent_id)
            self.assertEqual(result.call.provider_agent_id, "unknown-agent")
            self.assertEqual(result.call.tenant_id, tenant.id)

    def test_official_unjoined_ended_event_normalizes_as_unanswered(self):
        tenant, _ = self.seed_tenant_and_agent()

        with SessionLocal() as db:
            result = UltravoxIngestionService(db).ingest_event(
                self.official_payload(
                    "call.ended",
                    "uvx-unjoined",
                    tenant,
                    ended="2026-05-02T14:00:30Z",
                    endReason="unjoined",
                    billingStatus="BILLING_STATUS_FREE_ZERO_EFFECTIVE_DURATION",
                )
            )

            self.assertEqual(result.call.provider_status, "unjoined")
            self.assertEqual(result.call.normalized_status, "unanswered")

    def test_official_out_of_order_started_event_does_not_downgrade_terminal_call(self):
        tenant, _ = self.seed_tenant_and_agent()

        with SessionLocal() as db:
            service = UltravoxIngestionService(db)
            service.ingest_event(
                self.official_payload(
                    "call.ended",
                    "uvx-out-of-order",
                    tenant,
                    joined="2026-05-02T14:00:12Z",
                    ended="2026-05-02T14:03:20Z",
                    endReason="hangup",
                )
            )
            service.ingest_event(
                self.official_payload("call.started", "uvx-out-of-order", tenant)
            )

            call = db.query(Call).filter_by(external_call_id="uvx-out-of-order").one()
            self.assertEqual(db.query(CallEvent).count(), 2)
            self.assertEqual(call.provider_status, "hangup")
            self.assertEqual(call.normalized_status, "answered")

    def test_missing_official_tenant_metadata_is_rejected(self):
        response = self.client.post(
            "/api/v1/integrations/ultravox/events",
            headers={"x-serviai-webhook-secret": "test-webhook-secret"},
            json=self.official_payload(
                "call.started",
                "uvx-missing-tenant",
                metadata={},
            ),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Unable to resolve tenant for Ultravox payload")

    def test_legacy_flat_payload_remains_supported(self):
        tenant, agent = self.seed_tenant_and_agent()

        with SessionLocal() as db:
            result = UltravoxIngestionService(db).ingest_event(
                {
                    "eventType": "call.started",
                    "eventId": "evt-legacy",
                    "callId": "uvx-legacy",
                    "tenant_id": tenant.id,
                    "agentId": agent.external_agent_id,
                    "status": "started",
                    "startedAt": "2026-05-02T16:00:00Z",
                }
            )

            self.assertEqual(result.event.event_type, "call.started")
            self.assertEqual(result.call.external_call_id, "uvx-legacy")
            self.assertEqual(result.call.agent_id, agent.id)

    def test_webhook_rejects_invalid_secret(self):
        tenant, _ = self.seed_tenant_and_agent()

        response = self.client.post(
            "/api/v1/integrations/ultravox/events",
            headers={"x-serviai-webhook-secret": "wrong"},
            json=self.official_payload("call.started", "uvx-secret", tenant),
        )

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
