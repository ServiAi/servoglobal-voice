"""PostgreSQL-only Analytics guarantees: call/agent/event convergence, isolation and usage facts."""

from __future__ import annotations

import os
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

ANALYTICS_TEST_DATABASE_URL = os.environ.get("ANALYTICS_TEST_DATABASE_URL")
if ANALYTICS_TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = ANALYTICS_TEST_DATABASE_URL
os.environ.setdefault("ULTRAVOX_API_KEY", "test")

import app.models  # noqa: F401 - register every mapped table before create_all
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.modules.agents.infrastructure.models import TenantAgent
from app.modules.analytics.application.agent_service import AnalyticsAgentService
from app.modules.analytics.application.call_service import AnalyticsCallService
from app.modules.analytics.application.ports import (
    AgentDescription,
    ProjectionEvent,
    ProjectionSession,
)
from app.modules.analytics.application.projection_service import VoiceCallProjectionService
from app.modules.analytics.infrastructure.models import Agent, Call, CallEvent, MetricSnapshotDaily
from app.modules.analytics.public import (
    AgentUpsertCommand,
    AmbiguousAnalyticsAgentError,
    AnalyticsAgentDirectory,
    AnalyticsCallLedger,
    AnalyticsConflictError,
    AnalyticsMaintenance,
    AnalyticsUsageFacts,
    PersistCallCommand,
    PersistCallEventCommand,
    VoiceCallProjectionFacade,
)
from app.modules.identity.infrastructure.models import Tenant
from app.modules.voice.infrastructure.models import VoiceSession, VoiceSessionEvent

EXPECTED_DATABASE = "serviai_analytics_test"
WORKERS = 6
START = datetime(2026, 5, 2, 14, 0, tzinfo=UTC)


def concurrently(workers: int, task):
    barrier = Barrier(workers)

    def run(index):
        barrier.wait(timeout=15)
        return task(index)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run, i) for i in range(workers)]
        return [future.result(timeout=60) for future in futures]


class _StubSessions:
    def __init__(self, session: ProjectionSession) -> None:
        self.session = session

    def get_session(self, session_id, tenant_id, *, lock=True):
        return self.session


class _StubCrm:
    """No CRM call is linked to the session, so none of these methods is reached."""


class _SlowCatalog:
    """Describing the agent is the step right before both rows are created: it lines the racers up."""

    def describe_agent(self, tenant_id, agent_id, agent_version_id):
        time.sleep(0.3)
        return AgentDescription(name="Agente", status="active")


@unittest.skipUnless(ANALYTICS_TEST_DATABASE_URL, "ANALYTICS_TEST_DATABASE_URL not set")
class AnalyticsPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = make_url(ANALYTICS_TEST_DATABASE_URL)
        if url.get_backend_name() != "postgresql" or url.database != EXPECTED_DATABASE:
            raise RuntimeError(f"Analytics tests require the dedicated PostgreSQL database {EXPECTED_DATABASE}")
        cls.engine = create_engine(ANALYTICS_TEST_DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=10)
        Base.metadata.drop_all(cls.engine)
        Base.metadata.create_all(cls.engine)
        # Open the pool up front: connecting lazily would serialize the racers and hide the races.
        warm = [cls.engine.connect() for _ in range(WORKERS + 2)]
        for connection in warm:
            connection.close()
        cls.Session = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def tenant(self) -> str:
        with self.Session() as db:
            tenant = Tenant(name="Analytics test", slug=f"analytics-{uuid.uuid4().hex}", timezone="UTC")
            db.add(tenant)
            db.commit()
            return tenant.id

    def count(self, model, *conditions) -> int:
        with self.Session() as db:
            return db.scalar(select(func.count()).select_from(model).where(*conditions))

    def call_command(self, tenant_id: str, external_call_id: str, **overrides) -> PersistCallCommand:
        values = {
            "tenant_id": tenant_id,
            "external_provider": "ultravox",
            "external_call_id": external_call_id,
            "provider_status": "started",
            "started_at": START,
            "partial_update": True,
        }
        values.update(overrides)
        return PersistCallCommand(**values)

    # -- calls ----------------------------------------------------------------------------------

    def test_concurrent_persist_of_the_same_call_converges_on_one_row(self):
        tenant_id, external_id = self.tenant(), f"call-{uuid.uuid4().hex}"
        original_new_call = AnalyticsCallService._new_call

        def slow_new_call(service, command):
            call = original_new_call(service, command)
            time.sleep(0.4)  # every racer has already seen "no call" before anyone inserts
            return call

        def persist(index):
            with self.Session() as db:
                return AnalyticsCallLedger(db).persist_call(
                    self.call_command(tenant_id, external_id, duration_seconds=index + 1)
                )

        with patch.object(AnalyticsCallService, "_new_call", slow_new_call):
            views = concurrently(WORKERS, persist)

        self.assertEqual(len({view.id for view in views}), 1)
        self.assertEqual(self.count(Call, Call.tenant_id == tenant_id, Call.external_call_id == external_id), 1)

    def test_the_same_external_call_id_is_a_distinct_call_per_tenant(self):
        tenant_a, tenant_b, external_id = self.tenant(), self.tenant(), f"call-{uuid.uuid4().hex}"
        with self.Session() as db:
            first = AnalyticsCallLedger(db).persist_call(self.call_command(tenant_a, external_id))
            second = AnalyticsCallLedger(db).persist_call(self.call_command(tenant_b, external_id))
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(self.count(Call, Call.external_call_id == external_id), 2)

    def test_a_late_in_progress_update_does_not_reopen_a_finished_call(self):
        tenant_id, external_id = self.tenant(), f"call-{uuid.uuid4().hex}"
        with self.Session() as db:
            ledger = AnalyticsCallLedger(db)
            ledger.persist_call(self.call_command(tenant_id, external_id, provider_status="completed"))
            late = ledger.persist_call(self.call_command(tenant_id, external_id, provider_status="in_progress"))
        self.assertEqual(late.normalized_status, "answered")
        self.assertEqual(late.provider_status, "completed")

    def test_a_late_in_progress_update_loses_the_race_against_the_final_status(self):
        tenant_id, external_id = self.tenant(), f"call-{uuid.uuid4().hex}"
        with self.Session() as db:
            AnalyticsCallLedger(db).persist_call(self.call_command(tenant_id, external_id))

        def update(index):
            status = "completed" if index == 0 else "in_progress"
            with self.Session() as db:
                return AnalyticsCallLedger(db).persist_call(
                    self.call_command(tenant_id, external_id, provider_status=status)
                )

        concurrently(WORKERS, update)
        with self.Session() as db:
            status = db.scalar(select(Call.normalized_status).where(Call.tenant_id == tenant_id))
        self.assertEqual(status, "answered")

    # -- events ---------------------------------------------------------------------------------

    def test_concurrent_events_with_one_dedup_key_are_recorded_exactly_once(self):
        tenant_id, external_id = self.tenant(), f"call-{uuid.uuid4().hex}"
        dedup_key = f"ultravox:{external_id}:call.ended"
        with self.Session() as db:
            call_id = AnalyticsCallLedger(db).persist_call(self.call_command(tenant_id, external_id)).id
        original_find = AnalyticsCallService._find_event

        def slow_find(service, key):
            found = original_find(service, key)
            time.sleep(0.3)  # losers decide to insert before the winner commits
            return found

        def claim(_index):
            with self.Session() as db:
                return AnalyticsCallLedger(db).claim_event(
                    PersistCallEventCommand(tenant_id, call_id, "call.ended", {"event_type": "call.ended"}, dedup_key=dedup_key)
                )

        with patch.object(AnalyticsCallService, "_find_event", slow_find):
            claims = concurrently(WORKERS, claim)

        self.assertEqual(sum(1 for item in claims if item.created), 1)
        self.assertEqual(len({item.event.id for item in claims}), 1)
        self.assertEqual(self.count(CallEvent, CallEvent.dedup_key == dedup_key), 1)

    def test_a_dedup_key_owned_by_another_tenant_is_never_adopted(self):
        tenant_a, tenant_b = self.tenant(), self.tenant()
        dedup_key = f"shared:{uuid.uuid4().hex}"
        with self.Session() as db:
            ledger = AnalyticsCallLedger(db)
            call_a = ledger.persist_call(self.call_command(tenant_a, "a"))
            call_b = ledger.persist_call(self.call_command(tenant_b, "b"))
            ledger.claim_event(PersistCallEventCommand(tenant_a, call_a.id, "call.started", {}, dedup_key=dedup_key))
            with self.assertRaises(AnalyticsConflictError):
                ledger.claim_event(PersistCallEventCommand(tenant_b, call_b.id, "call.started", {}, dedup_key=dedup_key))

    def test_events_without_a_dedup_key_always_insert(self):
        tenant_id = self.tenant()
        with self.Session() as db:
            ledger = AnalyticsCallLedger(db)
            call = ledger.persist_call(self.call_command(tenant_id, "plain"))
            for _ in range(2):
                self.assertTrue(ledger.claim_event(PersistCallEventCommand(tenant_id, call.id, "call.updated", {})).created)
        self.assertEqual(self.count(CallEvent, CallEvent.tenant_id == tenant_id), 2)

    # -- agents ---------------------------------------------------------------------------------

    def test_concurrent_agent_upserts_converge_on_one_agent(self):
        tenant_id, external_id = self.tenant(), f"agent-{uuid.uuid4().hex}"
        original_select = AnalyticsAgentService._select_identity

        def slow_select(service, *args, **kwargs):
            found = original_select(service, *args, **kwargs)
            if found is None:
                time.sleep(0.4)
            return found

        def upsert(index):
            with self.Session() as db:
                view = AnalyticsAgentDirectory(db).upsert_provider_agent(
                    AgentUpsertCommand(tenant_id, "ultravox", external_id, name=f"Agente {index}", channel_type="voice")
                )
                db.commit()
                return view

        with patch.object(AnalyticsAgentService, "_select_identity", slow_select):
            views = concurrently(WORKERS, upsert)

        self.assertEqual(len({view.id for view in views}), 1)
        self.assertEqual(self.count(Agent, Agent.tenant_id == tenant_id, Agent.external_agent_id == external_id), 1)

    def test_an_ambiguous_agent_identifier_fails_closed_instead_of_picking_a_tenant(self):
        tenant_a, tenant_b, external_id = self.tenant(), self.tenant(), f"shared-agent-{uuid.uuid4().hex}"
        with self.Session() as db:
            agents = AnalyticsAgentDirectory(db)
            for tenant_id in (tenant_a, tenant_b):
                agents.upsert_provider_agent(AgentUpsertCommand(tenant_id, "ultravox", external_id, name="Agente"))
            db.commit()
            with self.assertRaises(AmbiguousAnalyticsAgentError):
                agents.resolve_unique_external_agent(external_id)
            # a tenant-scoped lookup is never ambiguous
            self.assertEqual(agents.find_by_provider_identity(tenant_a, "ultravox", external_id).tenant_id, tenant_a)

    def test_a_unique_active_agent_resolves_and_an_inactive_one_does_not(self):
        tenant_id, external_id = self.tenant(), f"agent-{uuid.uuid4().hex}"
        with self.Session() as db:
            agents = AnalyticsAgentDirectory(db)
            agents.upsert_provider_agent(AgentUpsertCommand(tenant_id, "ultravox", external_id, name="Agente"))
            self.assertEqual(agents.resolve_unique_external_agent(external_id).tenant_id, tenant_id)
            agents.upsert_provider_agent(AgentUpsertCommand(tenant_id, "ultravox", external_id, name="Agente", status="inactive"))
            with self.assertRaises(LookupError):
                agents.resolve_unique_external_agent(external_id)

    # -- projection -----------------------------------------------------------------------------

    def _projection_session(self, tenant_id: str, agent_id: str | None) -> ProjectionSession:
        return ProjectionSession(
            id=f"session-{uuid.uuid4().hex}", tenant_id=tenant_id, status="ended", agent_id=agent_id,
            deleted_agent_id=None, agent_version_id=None, provider="ultravox", provider_session_id=None,
            channel="webrtc", direction="internal", crm_voice_call_id=None, requested_at=START, started_at=START,
            connected_at=START + timedelta(seconds=5), ended_at=START + timedelta(seconds=65),
            context_contact_id=None, context_lead_id=None, livekit_room_name=None, livekit_dispatch_id=None,
            livekit_sip_trunk_id=None, livekit_sip_participant_identity=None, sip_call_id=None,
            events=(ProjectionEvent("e1", "voice.session.connected", 1, START, None, None),),
        )

    def test_concurrent_projections_of_one_session_create_a_single_call_and_agent(self):
        tenant_id = self.tenant()
        session = self._projection_session(tenant_id, str(uuid.uuid4()))

        def project(_index):
            with self.Session() as db:
                service = VoiceCallProjectionService(
                    db, sessions=_StubSessions(session), crm=_StubCrm(), agent_catalog=_SlowCatalog()
                )
                return service.project_session(session.id, tenant_id=tenant_id)

        views = concurrently(WORKERS, project)

        self.assertEqual(len({view.id for view in views}), 1)
        self.assertEqual(self.count(Call, Call.tenant_id == tenant_id), 1)
        self.assertEqual(self.count(Agent, Agent.tenant_id == tenant_id), 1)
        self.assertEqual(views[0].normalized_status, "answered")
        self.assertEqual(views[0].duration_seconds, 65)  # connected event at START, ended at +65s

    def test_projections_without_an_agent_converge_through_the_call_unique_constraint(self):
        tenant_id = self.tenant()
        session = self._projection_session(tenant_id, None)
        original = VoiceCallProjectionService._locked_call

        def slow_locked_call(service, *args, **kwargs):
            time.sleep(0.4)  # every racer is past the session facts and about to look for the call
            return original(service, *args, **kwargs)

        def project(_index):
            with self.Session() as db:
                service = VoiceCallProjectionService(
                    db, sessions=_StubSessions(session), crm=_StubCrm(), agent_catalog=_SlowCatalog()
                )
                return service.project_session(session.id, tenant_id=tenant_id)

        with patch.object(VoiceCallProjectionService, "_locked_call", slow_locked_call):
            views = concurrently(WORKERS, project)

        self.assertEqual(len({view.id for view in views}), 1)
        self.assertEqual(self.count(Call, Call.tenant_id == tenant_id), 1)

    def test_the_real_voice_facade_projects_a_session_once_under_concurrency(self):
        tenant_id = self.tenant()
        with self.Session() as db:
            agent = TenantAgent(tenant_id=tenant_id, name="Agente de prueba", status="active")
            db.add(agent)
            db.flush()
            voice_session = VoiceSession(
                tenant_id=tenant_id, agent_id=agent.id, provider="ultravox", channel="webrtc", direction="internal",
                status="ended", requested_at=START, started_at=START, connected_at=START + timedelta(seconds=10),
                ended_at=START + timedelta(seconds=70), session_context_json={"schema_version": "1"},
            )
            db.add(voice_session)
            db.flush()
            db.add(VoiceSessionEvent(
                event_id=f"evt-{uuid.uuid4().hex}", tenant_id=tenant_id, voice_session_id=voice_session.id,
                event_type="voice.session.connected", source="livekit", sequence=1,
                occurred_at=START + timedelta(seconds=10), payload_json={},
            ))
            db.commit()
            session_id = voice_session.id

        def project(_index):
            with self.Session() as db:
                return VoiceCallProjectionFacade(db).project_session(session_id, tenant_id)

        views = concurrently(WORKERS, project)

        self.assertEqual(len({view.id for view in views}), 1)
        self.assertEqual(self.count(Call, Call.tenant_id == tenant_id, Call.external_call_id == f"voice-session:{session_id}"), 1)
        self.assertEqual(self.count(Agent, Agent.tenant_id == tenant_id), 1)
        with self.Session() as db:
            self.assertTrue(VoiceCallProjectionFacade(db).projection_exists(session_id, tenant_id))

    # -- usage facts ----------------------------------------------------------------------------

    def test_billed_minutes_use_a_closed_interval_and_only_finished_calls_of_the_tenant(self):
        tenant_id, other_tenant = self.tenant(), self.tenant()
        start, end = START, START + timedelta(days=30)
        rows = [
            (tenant_id, "10.00", "answered", start),                              # inclusive start
            (tenant_id, "5.50", "unanswered", end),                               # inclusive end
            (tenant_id, "100", "in_progress", start + timedelta(days=1)),         # still open
            (tenant_id, None, "answered", start + timedelta(days=2)),             # no billing data
            (tenant_id, "100", "answered", start - timedelta(seconds=1)),         # before
            (tenant_id, "100", "answered", end + timedelta(seconds=1)),           # after
            (other_tenant, "100", "answered", start + timedelta(days=3)),         # another tenant
        ]
        with self.Session() as db:
            for owner, minutes, status, started_at in rows:
                db.add(Call(
                    tenant_id=owner, external_provider="usage", external_call_id=uuid.uuid4().hex,
                    normalized_status=status, started_at=started_at,
                    billed_minutes=Decimal(minutes) if minutes is not None else None,
                ))
            db.commit()
            self.assertEqual(AnalyticsUsageFacts(db).billed_minutes(tenant_id, start, end), Decimal("15.50"))
            self.assertEqual(AnalyticsUsageFacts(db).billed_minutes(self.tenant(), start, end), Decimal("0"))

    # -- tenant cleanup and snapshots -----------------------------------------------------------

    def test_cleanup_removes_only_the_tenant_rows_in_foreign_key_order(self):
        tenant_id, other_tenant = self.tenant(), self.tenant()
        with self.Session() as db:
            for owner in (tenant_id, other_tenant):
                agent = AnalyticsAgentDirectory(db).upsert_provider_agent(
                    AgentUpsertCommand(owner, "ultravox", f"agent-{owner}", name="Agente")
                )
                call = AnalyticsCallLedger(db).persist_call(
                    self.call_command(owner, f"call-{owner}", agent_id=agent.id), commit=False
                )
                AnalyticsCallLedger(db).claim_event(
                    PersistCallEventCommand(owner, call.id, "call.started", {}), commit=False
                )
                db.add(MetricSnapshotDaily(tenant_id=owner, agent_id=agent.id, date=date(2026, 5, 2)))
            db.commit()

        with self.Session() as db:
            counts = AnalyticsMaintenance(db).cleanup_tenant(tenant_id)
            db.commit()

        self.assertEqual(counts, {"call_events": 1, "metric_snapshots": 1, "calls": 1, "agents": 1})
        for model in (Call, CallEvent, MetricSnapshotDaily, Agent):
            self.assertEqual(self.count(model, model.tenant_id == tenant_id), 0)
            self.assertEqual(self.count(model, model.tenant_id == other_tenant), 1)

    def test_metric_snapshot_identity_is_unique_per_tenant_agent_and_day(self):
        tenant_id = self.tenant()
        with self.Session() as db:
            agent = AnalyticsAgentDirectory(db).upsert_provider_agent(
                AgentUpsertCommand(tenant_id, "ultravox", "snap-agent", name="Agente")
            )
            db.add(MetricSnapshotDaily(tenant_id=tenant_id, agent_id=agent.id, date=date(2026, 5, 2)))
            db.commit()
            db.add(MetricSnapshotDaily(tenant_id=tenant_id, agent_id=agent.id, date=date(2026, 5, 2)))
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()


if __name__ == "__main__":
    unittest.main()
