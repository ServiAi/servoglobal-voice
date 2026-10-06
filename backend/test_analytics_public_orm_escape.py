"""Runs the public Analytics APIs for real and checks that no ORM instance ever comes back."""

from __future__ import annotations

import os
import typing
import unittest
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal

os.environ.setdefault("ULTRAVOX_API_KEY", "test")

import app.models  # noqa: F401  (register every ORM table before create_all)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.modules.analytics.infrastructure.models import Agent, Call, CallEvent, MetricSnapshotDaily
from app.modules.analytics.public import (
    AgentUpsertCommand,
    AnalyticsAgentDirectory,
    AnalyticsCallLedger,
    AnalyticsCallMetrics,
    AnalyticsDashboard,
    AnalyticsFacade,
    AnalyticsMaintenance,
    AnalyticsUsageFacts,
    CallLookup,
    CallView,
    DashboardFilters,
    NewAgentCommand,
    PersistCallCommand,
    PersistCallEventCommand,
    VoiceCallProjectionFacade,
)
from app.modules.identity.infrastructure.models import Tenant

ORM_TYPES = (Agent, Call, CallEvent, MetricSnapshotDaily)
START = datetime(2026, 5, 2, 14, 0, tzinfo=UTC)


def contains_orm(value: object, _depth: int = 0) -> bool:
    if isinstance(value, ORM_TYPES):
        return True
    if _depth > 6:
        return False
    if isinstance(value, Mapping):
        return any(contains_orm(v, _depth + 1) for v in value.values())
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(contains_orm(v, _depth + 1) for v in value)
    if hasattr(value, "__dataclass_fields__"):
        return any(contains_orm(getattr(value, name), _depth + 1) for name in value.__dataclass_fields__)
    return False


class AnalyticsPublicOrmEscapeTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.engine = engine
        self.db = sessionmaker(bind=engine, expire_on_commit=False)()
        tenant = Tenant(name="Acme", slug="acme", timezone="UTC", status="active")
        self.db.add(tenant)
        self.db.commit()
        self.tenant_id = tenant.id

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def assertNoOrm(self, label: str, value: object) -> None:
        self.assertFalse(contains_orm(value), f"{label} returned an ORM instance: {value!r}")

    def test_agent_directory_returns_views_only(self):
        agents = AnalyticsAgentDirectory(self.db)
        created = agents.create_agents(
            self.tenant_id, [NewAgentCommand(name="A", external_provider="ultravox", external_agent_id="x1")]
        )
        upserted = agents.upsert_provider_agent(
            AgentUpsertCommand(self.tenant_id, "ultravox", "x2", name="B", channel_type="voice")
        )
        self.db.commit()
        for label, value in {
            "create_agents": created,
            "upsert_provider_agent": upserted,
            "get": agents.get(self.tenant_id, upserted.id),
            "find_by_provider_identity": agents.find_by_provider_identity(self.tenant_id, "ultravox", "x2"),
            "list_for_tenant": agents.list_for_tenant(self.tenant_id),
            "resolve_unique_external_agent": agents.resolve_unique_external_agent("x2"),
        }.items():
            self.assertNoOrm(f"AnalyticsAgentDirectory.{label}", value)

    def test_call_ledger_lookup_metrics_and_usage_return_values_only(self):
        ledger = AnalyticsCallLedger(self.db)
        call = ledger.persist_call(
            PersistCallCommand(
                tenant_id=self.tenant_id,
                external_provider="ultravox",
                external_call_id="c1",
                provider_status="completed",
                started_at=START,
                summary="s",
                billed_minutes=Decimal("2.00"),
            )
        )
        claim = ledger.claim_event(
            PersistCallEventCommand(self.tenant_id, call.id, "call.started", {"k": "v"}, dedup_key="k1")
        )
        lookup = CallLookup(self.db)
        results = {
            "persist_call": call,
            "claim_event": claim,
            "add_event": ledger.add_event(PersistCallEventCommand(self.tenant_id, call.id, "call.ended", {})),
            "get": ledger.get(self.tenant_id, call.id),
            "find_by_external_call": ledger.find_by_external_call(self.tenant_id, "ultravox", "c1"),
            "list_reconciliation_candidates": ledger.list_reconciliation_candidates(self.tenant_id),
            "find_call_id": lookup.find_call_id(self.tenant_id, "ultravox", "c1"),
            "latest_summary": lookup.latest_summary(self.tenant_id, [call.id]),
            "statuses_by_ids": lookup.statuses_by_ids(self.tenant_id, [call.id]),
            "metrics": AnalyticsCallMetrics(self.db).metrics(self.tenant_id),
            "billed_minutes": AnalyticsUsageFacts(self.db).billed_minutes(self.tenant_id, START, START),
        }
        self.assertIsInstance(call, CallView)
        for label, value in results.items():
            self.assertNoOrm(label, value)

    def test_dashboard_returns_dtos_only(self):
        AnalyticsCallLedger(self.db).persist_call(
            PersistCallCommand(
                tenant_id=self.tenant_id, external_provider="ultravox", external_call_id="c1",
                provider_status="completed", started_at=START,
            )
        )
        dashboard, filters = AnalyticsDashboard(self.db), DashboardFilters()
        for label, value in {
            "kpis": dashboard.kpis(self.tenant_id, "UTC", filters),
            "trends": dashboard.trends(self.tenant_id, "UTC", filters),
            "status_distribution": dashboard.status_distribution(self.tenant_id, "UTC", filters),
            "agent_distribution": dashboard.agent_distribution(self.tenant_id, "UTC", filters),
            "heatmap": dashboard.heatmap(self.tenant_id, "UTC", filters),
            "recent_calls": dashboard.recent_calls(self.tenant_id, "UTC", filters, page=1, page_size=10),
        }.items():
            self.assertNoOrm(f"AnalyticsDashboard.{label}", value)

    def test_maintenance_returns_counts_and_facade_groups_the_apis(self):
        AnalyticsCallLedger(self.db).persist_call(
            PersistCallCommand(tenant_id=self.tenant_id, external_provider="p", external_call_id="c", started_at=START)
        )
        counts = AnalyticsMaintenance(self.db).cleanup_tenant(self.tenant_id)
        self.assertEqual(set(counts), {"call_events", "metric_snapshots", "calls", "agents"})
        self.assertEqual(counts["calls"], 1)
        self.assertNoOrm("cleanup_tenant", counts)
        facade = AnalyticsFacade(self.db)
        self.assertIsInstance(facade.calls(), AnalyticsCallLedger)
        self.assertIsInstance(facade.projection(), VoiceCallProjectionFacade)

    def test_projection_facade_declares_dto_return_types(self):
        hints = typing.get_type_hints(VoiceCallProjectionFacade.project_session)
        self.assertEqual(hints["return"], CallView | None)


if __name__ == "__main__":
    unittest.main()
