"""Import-light public Analytics API: facades over call facts, agents, dashboards and projection.

Every facade takes the caller's session (typed ``object`` to keep this module free of
SQLAlchemy) and loads its implementation lazily. Transaction rules are per method:
``commit=True`` (default) means Analytics commits (standalone ingestion); ``commit=False`` and the
maintenance/agent writes only flush and the caller owns the transaction. No method returns an ORM
instance."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from app.modules.analytics.contracts import (
    AgentUpsertCommand,
    AnalyticsAgentView,
    CallEventView,
    CallMetricsView,
    CallSummaryFact,
    CallView,
    DashboardAgentDistributionView,
    DashboardFilters,
    DashboardHeatmapView,
    DashboardKpisView,
    DashboardRecentCallsView,
    DashboardStatusDistributionView,
    DashboardTrendView,
    EventClaim,
    NewAgentCommand,
    PersistCallCommand,
    PersistCallEventCommand,
)
from app.modules.analytics.domain.errors import (
    AmbiguousAnalyticsAgentError,
    AnalyticsAgentNotFoundError,
    AnalyticsAgentTenantMismatchError,
    AnalyticsConflictError,
    AnalyticsError,
    AnalyticsTenantNotFoundError,
    CallNotFoundError,
    InvalidDashboardFilterError,
)
from app.modules.analytics.domain.statuses import (
    NORMALIZED_CALL_STATUSES,
    TERMINAL_CALL_STATUSES,
    CallStatusNormalizer,
)


class AnalyticsCallLedger:
    """Call facts and the call event ledger."""

    def __init__(self, db: object) -> None:
        self.db = db

    def _service(self):
        from app.modules.analytics.application.call_service import AnalyticsCallService

        return AnalyticsCallService(self.db)

    def get(self, tenant_id: str, call_id: str) -> CallView | None:
        return self._service().get(tenant_id, call_id)

    def find_by_external_call(self, tenant_id: str, external_provider: str, external_call_id: str) -> CallView | None:
        return self._service().find_by_external_call(tenant_id, external_provider, external_call_id)

    def list_reconciliation_candidates(self, tenant_id: str, limit: int = 100) -> tuple[CallView, ...]:
        return self._service().list_reconciliation_candidates(tenant_id, limit)

    def persist_call(self, command: PersistCallCommand, *, commit: bool = True) -> CallView:
        """Create-or-update; concurrent creators converge on one call. commit=False flushes only."""
        return self._service().persist_call(command, commit=commit)

    def claim_event(self, command: PersistCallEventCommand, *, commit: bool = True) -> EventClaim:
        """Exactly-once per dedup_key; ``created`` is False for the losers. commit=False flushes only."""
        return self._service().claim_event(command, commit=commit)

    def add_event(self, command: PersistCallEventCommand, *, commit: bool = True) -> CallEventView:
        return self._service().add_event(command, commit=commit)


class CallLookup:
    """Read-only call lookups."""

    def __init__(self, db: object) -> None:
        self.db = db

    def _queries(self):
        from app.modules.analytics.application.query_service import (
            AnalyticsQueryService,
        )

        return AnalyticsQueryService(self.db)

    def find_call_id(self, tenant_id: str, external_provider: str | None, external_call_id: str) -> str | None:
        return self._queries().find_call_id(tenant_id, external_provider, external_call_id)

    def latest_summary(self, tenant_id: str, call_ids: Sequence[str]) -> CallSummaryFact | None:
        return self._queries().latest_summary(tenant_id, call_ids)

    def statuses_by_ids(self, tenant_id: str, call_ids: Sequence[str]) -> dict[str, str]:
        return self._queries().statuses_by_ids(tenant_id, call_ids)


class AnalyticsCallMetrics:
    def __init__(self, db: object) -> None:
        self.db = db

    def metrics(
        self,
        tenant_id: str,
        *,
        started_from: datetime | None = None,
        started_to: datetime | None = None,
        call_ids: Sequence[str] | None = None,
    ) -> CallMetricsView:
        """``call_ids=None`` applies no id filter; an empty sequence matches no call."""
        from app.modules.analytics.application.query_service import (
            AnalyticsQueryService,
        )

        return AnalyticsQueryService(self.db).call_metrics(
            tenant_id, started_from=started_from, started_to=started_to, call_ids=call_ids
        )


class AnalyticsUsageFacts:
    def __init__(self, db: object) -> None:
        self.db = db

    def billed_minutes(self, tenant_id: str, period_start: datetime, period_end: datetime) -> Decimal:
        """Billed minutes of finished calls started within the closed interval [start, end]."""
        from app.modules.analytics.application.query_service import (
            AnalyticsQueryService,
        )

        return AnalyticsQueryService(self.db).billed_minutes(tenant_id, period_start, period_end)


class AnalyticsAgentDirectory:
    """The reporting/provider agent projection (``agents``), not the Agent Builder identity."""

    def __init__(self, db: object) -> None:
        self.db = db

    def _service(self):
        from app.modules.analytics.application.agent_service import (
            AnalyticsAgentService,
        )

        return AnalyticsAgentService(self.db)

    def get(self, tenant_id: str, agent_id: str) -> AnalyticsAgentView | None:
        return self._service().get(tenant_id, agent_id)

    def find_by_provider_identity(
        self, tenant_id: str, external_provider: str | None, external_agent_id: str | None
    ) -> AnalyticsAgentView | None:
        return self._service().find_by_provider_identity(tenant_id, external_provider, external_agent_id)

    def list_for_tenant(self, tenant_id: str) -> tuple[AnalyticsAgentView, ...]:
        return self._service().list_for_tenant(tenant_id)

    def create_agents(self, tenant_id: str, agents: Sequence[NewAgentCommand]) -> tuple[AnalyticsAgentView, ...]:
        """Flush only."""
        return self._service().create_agents(tenant_id, agents)

    def upsert_provider_agent(self, command: AgentUpsertCommand) -> AnalyticsAgentView:
        """Concurrent upserts of one identity converge on one agent. Flush only."""
        return self._service().upsert_provider_agent(command)

    def resolve_unique_external_agent(
        self, external_agent_id: str, *, external_provider: str | None = None
    ) -> AnalyticsAgentView:
        """The single active agent for a provider id; fails closed (not found / ambiguous)."""
        return self._service().resolve_unique_external_agent(external_agent_id, external_provider=external_provider)


class AnalyticsDashboard:
    """Call dashboards; the caller supplies the tenant id and its timezone."""

    def __init__(self, db: object) -> None:
        self.db = db

    def _service(self):
        from app.modules.analytics.application.dashboard_service import (
            AnalyticsDashboardService,
        )

        return AnalyticsDashboardService(self.db)

    def kpis(self, tenant_id: str, timezone: str | None, filters: DashboardFilters) -> DashboardKpisView:
        return self._service().kpis(tenant_id, timezone, filters)

    def trends(self, tenant_id: str, timezone: str | None, filters: DashboardFilters) -> DashboardTrendView:
        return self._service().trends(tenant_id, timezone, filters)

    def status_distribution(
        self, tenant_id: str, timezone: str | None, filters: DashboardFilters
    ) -> DashboardStatusDistributionView:
        return self._service().status_distribution(tenant_id, timezone, filters)

    def agent_distribution(
        self, tenant_id: str, timezone: str | None, filters: DashboardFilters
    ) -> DashboardAgentDistributionView:
        return self._service().agent_distribution(tenant_id, timezone, filters)

    def heatmap(self, tenant_id: str, timezone: str | None, filters: DashboardFilters) -> DashboardHeatmapView:
        return self._service().heatmap(tenant_id, timezone, filters)

    def recent_calls(
        self, tenant_id: str, timezone: str | None, filters: DashboardFilters, *, page: int, page_size: int
    ) -> DashboardRecentCallsView:
        return self._service().recent_calls(tenant_id, timezone, filters, page=page, page_size=page_size)


class AnalyticsMaintenance:
    def __init__(self, db: object) -> None:
        self.db = db

    def cleanup_tenant(self, tenant_id: str) -> dict[str, int]:
        """Deletes events, snapshots, calls and agents of the tenant. Flush only; the caller commits."""
        from app.modules.analytics.application.maintenance_service import (
            AnalyticsMaintenanceService,
        )

        return AnalyticsMaintenanceService(self.db).cleanup_tenant(tenant_id)


class VoiceCallProjectionFacade:
    """Satisfies Voice's VoiceProjectionPort (also used by Telephony)."""

    def __init__(self, db: object) -> None:
        self.db = db

    def _service(self):
        from app.modules.analytics.wiring import build_projection_service

        return build_projection_service(self.db)

    def on_runtime_event(self, session_id: str, tenant_id: str, event_type: str, occurred_at: datetime | None) -> None:
        """Inside the caller's transaction (flush only)."""
        self._service().apply_runtime_event(session_id, tenant_id, event_type, occurred_at)

    def reconcile(self, session_id: str, tenant_id: str) -> None:
        """Projects and commits."""
        self._service().reconcile_session(session_id, tenant_id=tenant_id)

    def project_session(self, session_id: str, tenant_id: str, *, commit: bool = True) -> CallView | None:
        """commit=True commits; commit=False flushes and the caller owns the transaction."""
        return self._service().project_session(session_id, tenant_id=tenant_id, commit=commit)

    def is_real_call(self, session_id: str, tenant_id: str | None = None) -> bool:
        """Whether the session carries real call evidence (read-only; holds no row locks)."""
        return self._service().is_real_call(session_id, tenant_id)

    def projection_exists(self, session_id: str, tenant_id: str) -> bool:
        return self._service().projection_exists(session_id, tenant_id)


class AnalyticsFacade:
    """Entry point grouping the Analytics facades for one session."""

    def __init__(self, db: object) -> None:
        self.db = db

    def calls(self) -> AnalyticsCallLedger:
        return AnalyticsCallLedger(self.db)

    def lookup(self) -> CallLookup:
        return CallLookup(self.db)

    def agents(self) -> AnalyticsAgentDirectory:
        return AnalyticsAgentDirectory(self.db)

    def usage(self) -> AnalyticsUsageFacts:
        return AnalyticsUsageFacts(self.db)

    def dashboard(self) -> AnalyticsDashboard:
        return AnalyticsDashboard(self.db)

    def maintenance(self) -> AnalyticsMaintenance:
        return AnalyticsMaintenance(self.db)

    def projection(self) -> VoiceCallProjectionFacade:
        return VoiceCallProjectionFacade(self.db)


__all__ = [
    "NORMALIZED_CALL_STATUSES",
    "TERMINAL_CALL_STATUSES",
    "AgentUpsertCommand",
    "AmbiguousAnalyticsAgentError",
    "AnalyticsAgentDirectory",
    "AnalyticsAgentNotFoundError",
    "AnalyticsAgentTenantMismatchError",
    "AnalyticsAgentView",
    "AnalyticsCallLedger",
    "AnalyticsCallMetrics",
    "AnalyticsConflictError",
    "AnalyticsDashboard",
    "AnalyticsError",
    "AnalyticsFacade",
    "AnalyticsMaintenance",
    "AnalyticsTenantNotFoundError",
    "AnalyticsUsageFacts",
    "CallEventView",
    "CallLookup",
    "CallMetricsView",
    "CallNotFoundError",
    "CallStatusNormalizer",
    "CallSummaryFact",
    "CallView",
    "DashboardAgentDistributionView",
    "DashboardFilters",
    "DashboardHeatmapView",
    "DashboardKpisView",
    "DashboardRecentCallsView",
    "DashboardStatusDistributionView",
    "DashboardTrendView",
    "EventClaim",
    "InvalidDashboardFilterError",
    "NewAgentCommand",
    "PersistCallCommand",
    "PersistCallEventCommand",
    "VoiceCallProjectionFacade",
]
