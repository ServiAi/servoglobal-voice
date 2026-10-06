"""Dashboard read models over call facts. Returns frozen DTOs; the API layer shapes the HTTP response."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from app.modules.analytics.contracts import (
    DashboardAgentDistributionView,
    DashboardAgentEntry,
    DashboardDistributionEntry,
    DashboardFilters,
    DashboardHeatmapCell,
    DashboardHeatmapView,
    DashboardKpisView,
    DashboardRecentCallsView,
    DashboardRecentCallView,
    DashboardStatusDistributionView,
    DashboardTrendPoint,
    DashboardTrendView,
)
from app.modules.analytics.domain.dashboard import (
    UNASSIGNED_AGENT_LABEL,
    ResolvedFilters,
    decimal_sum,
    decimal_to_float,
    local_datetime,
    nullable_decimal_to_float,
    percentage,
    resolve_filters,
    tenant_timezone,
    validate_page,
)
from app.modules.analytics.domain.statuses import (
    ACTIVE_STATUS,
    ANSWERED_STATUS,
    NORMALIZED_CALL_STATUSES,
    UNANSWERED_STATUS,
)
from app.modules.analytics.infrastructure.models import Agent, Call


@dataclass(frozen=True)
class _CallRow:
    call: Call
    agent_name: str | None


class AnalyticsDashboardService:
    """Every method takes the caller's ``tenant_id`` and ``timezone`` explicitly."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def kpis(self, tenant_id: str, timezone: str | None, filters: DashboardFilters) -> DashboardKpisView:
        rows = self._list_filtered_calls(tenant_id, timezone, filters)
        calls_total = len(rows)
        calls_answered = sum(1 for row in rows if row.call.normalized_status == ANSWERED_STATUS)
        calls_unanswered = sum(1 for row in rows if row.call.normalized_status == UNANSWERED_STATUS)
        active_calls = sum(1 for row in rows if row.call.normalized_status == ACTIVE_STATUS)
        eligible_calls = sum(1 for row in rows if row.call.normalized_status != ACTIVE_STATUS)
        answered_durations = [
            row.call.duration_seconds
            for row in rows
            if row.call.normalized_status == ANSWERED_STATUS and row.call.duration_seconds is not None
        ]
        return DashboardKpisView(
            calls_total=calls_total,
            calls_answered=calls_answered,
            calls_unanswered=calls_unanswered,
            answer_rate=percentage(calls_answered, eligible_calls),
            avg_duration_seconds=round(sum(answered_durations) / len(answered_durations), 2)
            if answered_durations
            else 0.0,
            total_duration_seconds=sum(row.call.duration_seconds or 0 for row in rows),
            billed_minutes=decimal_sum(row.call.billed_minutes for row in rows),
            active_calls=active_calls,
        )

    def trends(self, tenant_id: str, timezone: str | None, filters: DashboardFilters) -> DashboardTrendView:
        rows = self._list_filtered_calls(tenant_id, timezone, filters)
        zone = tenant_timezone(timezone)
        buckets: dict[date, dict[str, int | float]] = {}
        for row in rows:
            local_date = local_datetime(row.call.started_at, zone).date()
            bucket = buckets.setdefault(
                local_date,
                {
                    "calls_total": 0,
                    "calls_answered": 0,
                    "calls_unanswered": 0,
                    "billed_minutes": 0.0,
                    "total_duration_seconds": 0,
                },
            )
            bucket["calls_total"] += 1
            if row.call.normalized_status == ANSWERED_STATUS:
                bucket["calls_answered"] += 1
            if row.call.normalized_status == UNANSWERED_STATUS:
                bucket["calls_unanswered"] += 1
            bucket["billed_minutes"] += decimal_to_float(row.call.billed_minutes)
            bucket["total_duration_seconds"] += row.call.duration_seconds or 0

        return DashboardTrendView(
            series=tuple(
                DashboardTrendPoint(
                    date=day,
                    calls_total=int(bucket["calls_total"]),
                    calls_answered=int(bucket["calls_answered"]),
                    calls_unanswered=int(bucket["calls_unanswered"]),
                    billed_minutes=round(float(bucket["billed_minutes"]), 2),
                    total_duration_seconds=int(bucket["total_duration_seconds"]),
                )
                for day, bucket in sorted(buckets.items())
            )
        )

    def status_distribution(
        self, tenant_id: str, timezone: str | None, filters: DashboardFilters
    ) -> DashboardStatusDistributionView:
        rows = self._list_filtered_calls(tenant_id, timezone, filters)
        total = len(rows)
        counts: dict[str, int] = {}
        for row in rows:
            counts[row.call.normalized_status] = counts.get(row.call.normalized_status, 0) + 1

        ordered_statuses = list(NORMALIZED_CALL_STATUSES) + sorted(
            status_key for status_key in counts if status_key not in NORMALIZED_CALL_STATUSES
        )
        return DashboardStatusDistributionView(
            items=tuple(
                DashboardDistributionEntry(
                    key=status_key,
                    label=status_key.replace("_", " ").title(),
                    calls=counts[status_key],
                    percentage=percentage(counts[status_key], total),
                )
                for status_key in ordered_statuses
                if counts.get(status_key, 0) > 0
            )
        )

    def agent_distribution(
        self, tenant_id: str, timezone: str | None, filters: DashboardFilters
    ) -> DashboardAgentDistributionView:
        rows = self._list_filtered_calls(tenant_id, timezone, filters)
        total = len(rows)
        counts: dict[str | None, dict[str, str | int | None]] = {}
        for row in rows:
            agent_id = row.call.agent_id
            bucket = counts.setdefault(
                agent_id,
                {"agent_id": agent_id, "agent_name": row.agent_name or UNASSIGNED_AGENT_LABEL, "calls": 0},
            )
            bucket["calls"] = int(bucket["calls"]) + 1

        return DashboardAgentDistributionView(
            items=tuple(
                DashboardAgentEntry(
                    agent_id=bucket["agent_id"],
                    agent_name=str(bucket["agent_name"]),
                    calls=int(bucket["calls"]),
                    percentage=percentage(int(bucket["calls"]), total),
                )
                for bucket in sorted(
                    counts.values(),
                    key=lambda item: (str(item["agent_name"]) == UNASSIGNED_AGENT_LABEL, str(item["agent_name"])),
                )
            )
        )

    def heatmap(self, tenant_id: str, timezone: str | None, filters: DashboardFilters) -> DashboardHeatmapView:
        rows = self._list_filtered_calls(tenant_id, timezone, filters)
        zone = tenant_timezone(timezone)
        buckets: dict[tuple[date, int], int] = {}
        for row in rows:
            local_started_at = local_datetime(row.call.started_at, zone)
            key = (local_started_at.date(), local_started_at.hour)
            buckets[key] = buckets.get(key, 0) + 1

        return DashboardHeatmapView(
            matrix=tuple(
                DashboardHeatmapCell(day=day, hour=hour, calls=calls) for (day, hour), calls in sorted(buckets.items())
            )
        )

    def recent_calls(
        self,
        tenant_id: str,
        timezone: str | None,
        filters: DashboardFilters,
        *,
        page: int,
        page_size: int,
    ) -> DashboardRecentCallsView:
        validate_page(page, page_size)
        statement, conditions = self._filtered_call_statement(tenant_id, self._resolve(timezone, filters))
        total = self.db.scalar(select(func.count()).select_from(Call).where(and_(*conditions))) or 0
        rows = self.db.execute(
            statement.order_by(Call.started_at.desc(), Call.id.desc()).offset((page - 1) * page_size).limit(page_size)
        ).all()

        return DashboardRecentCallsView(
            items=tuple(
                DashboardRecentCallView(
                    id=call.id,
                    started_at=call.started_at,
                    duration_seconds=call.duration_seconds,
                    billed_minutes=nullable_decimal_to_float(call.billed_minutes),
                    agent_name=agent_name or UNASSIGNED_AGENT_LABEL,
                    summary=call.summary,
                    short_summary=call.short_summary,
                    status=call.normalized_status,
                    external_provider=call.external_provider,
                    channel=call.channel,
                    direction=call.direction,
                )
                for call, agent_name in rows
            ),
            page=page,
            page_size=page_size,
            total=total,
        )

    def _resolve(self, timezone: str | None, filters: DashboardFilters) -> ResolvedFilters:
        return resolve_filters(
            from_value=filters.from_value,
            to_value=filters.to_value,
            agent_id=filters.agent_id,
            status=filters.status,
            timezone=tenant_timezone(timezone),
        )

    def _list_filtered_calls(self, tenant_id: str, timezone: str | None, filters: DashboardFilters) -> list[_CallRow]:
        statement, _ = self._filtered_call_statement(tenant_id, self._resolve(timezone, filters))
        rows = self.db.execute(statement.order_by(Call.started_at.asc(), Call.id.asc())).all()
        return [_CallRow(call=call, agent_name=agent_name) for call, agent_name in rows]

    @staticmethod
    def _filtered_call_statement(
        tenant_id: str, resolved: ResolvedFilters
    ) -> tuple[Select[tuple[Call, str | None]], list]:
        conditions = [Call.tenant_id == tenant_id]
        if resolved.from_datetime is not None:
            conditions.append(Call.started_at >= resolved.from_datetime)
        if resolved.to_datetime is not None:
            conditions.append(Call.started_at <= resolved.to_datetime)
        if resolved.agent_id:
            conditions.append(Call.agent_id == resolved.agent_id)
        if resolved.status:
            conditions.append(Call.normalized_status == resolved.status)

        statement = (
            select(Call, Agent.name)
            .outerjoin(Agent, and_(Agent.id == Call.agent_id, Agent.tenant_id == tenant_id))
            .where(and_(*conditions))
        )
        return statement, conditions
