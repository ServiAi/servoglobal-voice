from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from app.models.analytics import NORMALIZED_CALL_STATUSES, Agent, Call
from app.models.identity import Tenant
from app.schemas.dashboard import (
    DashboardAgentDistributionItem,
    DashboardAgentDistributionResponse,
    DashboardDistributionItem,
    DashboardHeatmapItem,
    DashboardHeatmapResponse,
    DashboardKpisResponse,
    DashboardRecentCallItem,
    DashboardRecentCallsResponse,
    DashboardStatusDistributionResponse,
    DashboardTrendItem,
    DashboardTrendsResponse,
)


UNASSIGNED_AGENT_LABEL = "Unassigned"
ANSWERED_STATUS = "answered"
UNANSWERED_STATUS = "unanswered"
ACTIVE_STATUS = "in_progress"


@dataclass(frozen=True)
class DashboardFilters:
    from_value: str | None = None
    to_value: str | None = None
    agent_id: str | None = None
    status: str | None = None


@dataclass(frozen=True)
class _ResolvedFilters:
    from_datetime: datetime | None
    to_datetime: datetime | None
    agent_id: str | None
    status: str | None


@dataclass(frozen=True)
class _CallRow:
    call: Call
    agent_name: str | None


class DashboardAnalyticsService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_kpis(self, tenant: Tenant, filters: DashboardFilters) -> DashboardKpisResponse:
        rows = self._list_filtered_calls(tenant, filters)
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

        return DashboardKpisResponse(
            calls_total=calls_total,
            calls_answered=calls_answered,
            calls_unanswered=calls_unanswered,
            answer_rate=self._percentage(calls_answered, eligible_calls),
            avg_duration_seconds=round(sum(answered_durations) / len(answered_durations), 2)
            if answered_durations
            else 0.0,
            total_duration_seconds=sum(row.call.duration_seconds or 0 for row in rows),
            billed_minutes=self._decimal_sum(row.call.billed_minutes for row in rows),
            active_calls=active_calls,
        )

    def get_trends(self, tenant: Tenant, filters: DashboardFilters) -> DashboardTrendsResponse:
        rows = self._list_filtered_calls(tenant, filters)
        timezone = self._tenant_timezone(tenant)
        buckets: dict[date, dict[str, int | float]] = {}
        for row in rows:
            local_date = self._local_datetime(row.call.started_at, timezone).date()
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
            bucket["billed_minutes"] += self._decimal_to_float(row.call.billed_minutes)
            bucket["total_duration_seconds"] += row.call.duration_seconds or 0

        return DashboardTrendsResponse(
            series=[
                DashboardTrendItem(
                    date=day,
                    calls_total=int(bucket["calls_total"]),
                    calls_answered=int(bucket["calls_answered"]),
                    calls_unanswered=int(bucket["calls_unanswered"]),
                    billed_minutes=round(float(bucket["billed_minutes"]), 2),
                    total_duration_seconds=int(bucket["total_duration_seconds"]),
                )
                for day, bucket in sorted(buckets.items())
            ]
        )

    def get_status_distribution(
        self, tenant: Tenant, filters: DashboardFilters
    ) -> DashboardStatusDistributionResponse:
        rows = self._list_filtered_calls(tenant, filters)
        total = len(rows)
        counts: dict[str, int] = {}
        for row in rows:
            status_key = row.call.normalized_status
            counts[status_key] = counts.get(status_key, 0) + 1

        ordered_statuses = list(NORMALIZED_CALL_STATUSES) + sorted(
            status_key for status_key in counts if status_key not in NORMALIZED_CALL_STATUSES
        )
        return DashboardStatusDistributionResponse(
            items=[
                DashboardDistributionItem(
                    key=status_key,
                    label=status_key.replace("_", " ").title(),
                    calls=counts[status_key],
                    percentage=self._percentage(counts[status_key], total),
                )
                for status_key in ordered_statuses
                if counts.get(status_key, 0) > 0
            ]
        )

    def get_agent_distribution(
        self, tenant: Tenant, filters: DashboardFilters
    ) -> DashboardAgentDistributionResponse:
        rows = self._list_filtered_calls(tenant, filters)
        total = len(rows)
        counts: dict[str | None, dict[str, str | int | None]] = {}
        for row in rows:
            agent_id = row.call.agent_id
            bucket = counts.setdefault(
                agent_id,
                {
                    "agent_id": agent_id,
                    "agent_name": row.agent_name or UNASSIGNED_AGENT_LABEL,
                    "calls": 0,
                },
            )
            bucket["calls"] = int(bucket["calls"]) + 1

        return DashboardAgentDistributionResponse(
            items=[
                DashboardAgentDistributionItem(
                    agent_id=bucket["agent_id"],
                    agent_name=str(bucket["agent_name"]),
                    calls=int(bucket["calls"]),
                    percentage=self._percentage(int(bucket["calls"]), total),
                )
                for bucket in sorted(
                    counts.values(),
                    key=lambda item: (str(item["agent_name"]) == UNASSIGNED_AGENT_LABEL, str(item["agent_name"])),
                )
            ]
        )

    def get_heatmap(self, tenant: Tenant, filters: DashboardFilters) -> DashboardHeatmapResponse:
        rows = self._list_filtered_calls(tenant, filters)
        timezone = self._tenant_timezone(tenant)
        buckets: dict[tuple[date, int], int] = {}
        for row in rows:
            local_started_at = self._local_datetime(row.call.started_at, timezone)
            key = (local_started_at.date(), local_started_at.hour)
            buckets[key] = buckets.get(key, 0) + 1

        return DashboardHeatmapResponse(
            matrix=[
                DashboardHeatmapItem(day=day, hour=hour, calls=calls)
                for (day, hour), calls in sorted(buckets.items())
            ]
        )

    def get_recent_calls(
        self,
        tenant: Tenant,
        filters: DashboardFilters,
        *,
        page: int,
        page_size: int,
    ) -> DashboardRecentCallsResponse:
        if page < 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="page must be greater than or equal to 1",
            )
        if page_size < 1 or page_size > 100:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="page_size must be between 1 and 100",
            )

        statement, conditions = self._filtered_call_statement(tenant, filters)
        total = self.db.scalar(select(func.count()).select_from(Call).where(and_(*conditions))) or 0
        rows = self.db.execute(
            statement.order_by(Call.started_at.desc(), Call.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()

        return DashboardRecentCallsResponse(
            items=[
                DashboardRecentCallItem(
                    id=call.id,
                    started_at=call.started_at,
                    duration_seconds=call.duration_seconds,
                    billed_minutes=self._nullable_decimal_to_float(call.billed_minutes),
                    agent_name=agent_name or UNASSIGNED_AGENT_LABEL,
                    summary=call.summary,
                    short_summary=call.short_summary,
                    status=call.normalized_status,
                    external_provider=call.external_provider,
                )
                for call, agent_name in rows
            ],
            page=page,
            page_size=page_size,
            total=total,
        )

    def _list_filtered_calls(self, tenant: Tenant, filters: DashboardFilters) -> list[_CallRow]:
        statement, _ = self._filtered_call_statement(tenant, filters)
        rows = self.db.execute(statement.order_by(Call.started_at.asc(), Call.id.asc())).all()
        return [_CallRow(call=call, agent_name=agent_name) for call, agent_name in rows]

    def _filtered_call_statement(
        self, tenant: Tenant, filters: DashboardFilters
    ) -> tuple[Select[tuple[Call, str | None]], list]:
        resolved = self._resolve_filters(tenant, filters)
        conditions = [Call.tenant_id == tenant.id]
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
            .outerjoin(Agent, and_(Agent.id == Call.agent_id, Agent.tenant_id == tenant.id))
            .where(and_(*conditions))
        )
        return statement, conditions

    def _resolve_filters(self, tenant: Tenant, filters: DashboardFilters) -> _ResolvedFilters:
        if filters.status and filters.status not in NORMALIZED_CALL_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"status must be one of: {', '.join(NORMALIZED_CALL_STATUSES)}",
            )

        timezone = self._tenant_timezone(tenant)
        from_datetime = self._parse_filter_datetime(filters.from_value, timezone, is_end=False)
        to_datetime = self._parse_filter_datetime(filters.to_value, timezone, is_end=True)
        if from_datetime and to_datetime and from_datetime > to_datetime:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="from must be earlier than or equal to to",
            )

        return _ResolvedFilters(
            from_datetime=from_datetime,
            to_datetime=to_datetime,
            agent_id=filters.agent_id,
            status=filters.status,
        )

    def _parse_filter_datetime(
        self, value: str | None, timezone: ZoneInfo, *, is_end: bool
    ) -> datetime | None:
        if value is None or value == "":
            return None
        try:
            if "T" not in value and len(value) == 10:
                parsed_date = date.fromisoformat(value)
                local_datetime = datetime.combine(
                    parsed_date,
                    time.max if is_end else time.min,
                    tzinfo=timezone,
                )
                return local_datetime

            normalized = value.replace("Z", "+00:00")
            parsed_datetime = datetime.fromisoformat(normalized)
            if parsed_datetime.tzinfo is None:
                parsed_datetime = parsed_datetime.replace(tzinfo=timezone)
            return parsed_datetime
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="from and to must be ISO dates or datetimes",
            ) from exc

    def _tenant_timezone(self, tenant: Tenant) -> ZoneInfo:
        try:
            return ZoneInfo(tenant.timezone or "UTC")
        except ZoneInfoNotFoundError:
            return ZoneInfo("UTC")

    def _local_datetime(self, value: datetime, timezone: ZoneInfo) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone)
        return value.astimezone(timezone)

    def _percentage(self, numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 0.0
        return round((numerator / denominator) * 100, 2)

    def _decimal_sum(self, values) -> float:
        return round(sum(self._decimal_to_float(value) for value in values), 2)

    def _decimal_to_float(self, value: Decimal | int | float | None) -> float:
        if value is None:
            return 0.0
        return float(value)

    def _nullable_decimal_to_float(self, value: Decimal | int | float | None) -> float | None:
        if value is None:
            return None
        return float(value)
