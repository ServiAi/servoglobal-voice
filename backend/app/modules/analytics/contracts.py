"""Frozen Analytics data contracts (DTOs and commands); no ORM, no framework."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class AnalyticsAgentView:
    id: str
    tenant_id: str
    external_provider: str | None
    external_agent_id: str | None
    name: str
    channel_type: str | None
    status: str


@dataclass(frozen=True)
class CallView:
    id: str
    tenant_id: str
    external_call_id: str | None
    external_provider: str
    agent_id: str | None
    provider_agent_id: str | None
    provider_status: str | None
    normalized_status: str
    started_at: datetime
    joined_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    billed_minutes: Decimal | None
    summary: str | None
    short_summary: str | None
    recording_url: str | None
    direction: str | None
    channel: str | None
    customer_phone: str | None
    last_synced_at: datetime | None


@dataclass(frozen=True)
class CallEventView:
    id: str
    call_id: str
    tenant_id: str
    event_type: str
    provider_event_id: str | None
    dedup_key: str | None
    received_at: datetime


@dataclass(frozen=True)
class EventClaim:
    """``created`` is False when another writer already recorded the dedup key."""

    event: CallEventView
    created: bool


@dataclass(frozen=True)
class CallSummaryFact:
    summary: str | None
    short_summary: str | None
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: int | None


@dataclass(frozen=True)
class CallMetricsView:
    total_calls: int
    answered_calls: int
    unanswered_calls: int
    voicemail_calls: int
    failed_calls: int
    average_duration_seconds: float
    total_billed_minutes: float


@dataclass(frozen=True)
class PersistCallCommand:
    """``status_policy``: ``derive`` normalizes provider_status/normalized_status (default);
    ``explicit`` stores provider_status verbatim and only applies normalized_status when given;
    ``settle_open`` is ``explicit`` but only moves a call that is still in progress."""

    tenant_id: str
    external_provider: str
    started_at: datetime | None = None
    external_call_id: str | None = None
    agent_id: str | None = None
    provider_agent_id: str | None = None
    provider_status: str | None = None
    normalized_status: str | None = None
    joined_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: int | None = None
    billed_minutes: Decimal | int | float | str | None = None
    summary: str | None = None
    short_summary: str | None = None
    recording_url: str | None = None
    direction: str | None = None
    customer_phone: str | None = None
    last_synced_at: datetime | None = None
    partial_update: bool = False
    status_policy: str = "derive"


@dataclass(frozen=True)
class PersistCallEventCommand:
    tenant_id: str
    call_id: str
    event_type: str
    payload_json: Mapping[str, object]
    provider_event_id: str | None = None
    dedup_key: str | None = None
    received_at: datetime | None = None


@dataclass(frozen=True)
class AgentUpsertCommand:
    tenant_id: str
    external_provider: str | None
    external_agent_id: str | None
    name: str
    status: str = "active"
    channel_type: str | None = None


@dataclass(frozen=True)
class NewAgentCommand:
    name: str
    external_provider: str
    external_agent_id: str
    channel_type: str | None = None
    status: str = "active"


@dataclass(frozen=True)
class DashboardFilters:
    from_value: str | None = None
    to_value: str | None = None
    agent_id: str | None = None
    status: str | None = None


@dataclass(frozen=True)
class DashboardKpisView:
    calls_total: int
    calls_answered: int
    calls_unanswered: int
    answer_rate: float
    avg_duration_seconds: float
    total_duration_seconds: int
    billed_minutes: float
    active_calls: int


@dataclass(frozen=True)
class DashboardTrendPoint:
    date: date
    calls_total: int
    calls_answered: int
    calls_unanswered: int
    billed_minutes: float
    total_duration_seconds: int


@dataclass(frozen=True)
class DashboardTrendView:
    series: tuple[DashboardTrendPoint, ...]


@dataclass(frozen=True)
class DashboardDistributionEntry:
    key: str
    label: str
    calls: int
    percentage: float


@dataclass(frozen=True)
class DashboardStatusDistributionView:
    items: tuple[DashboardDistributionEntry, ...]


@dataclass(frozen=True)
class DashboardAgentEntry:
    agent_id: str | None
    agent_name: str
    calls: int
    percentage: float


@dataclass(frozen=True)
class DashboardAgentDistributionView:
    items: tuple[DashboardAgentEntry, ...]


@dataclass(frozen=True)
class DashboardHeatmapCell:
    day: date
    hour: int
    calls: int


@dataclass(frozen=True)
class DashboardHeatmapView:
    matrix: tuple[DashboardHeatmapCell, ...]


@dataclass(frozen=True)
class DashboardRecentCallView:
    id: str
    started_at: datetime
    duration_seconds: int | None
    billed_minutes: float | None
    agent_name: str
    summary: str | None
    short_summary: str | None
    status: str
    external_provider: str
    channel: str | None
    direction: str | None


@dataclass(frozen=True)
class DashboardRecentCallsView:
    items: tuple[DashboardRecentCallView, ...]
    page: int
    page_size: int
    total: int

