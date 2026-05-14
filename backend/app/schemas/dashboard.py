from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class DashboardKpisResponse(BaseModel):
    calls_total: int
    calls_answered: int
    calls_unanswered: int
    answer_rate: float
    avg_duration_seconds: float
    total_duration_seconds: int
    billed_minutes: float
    active_calls: int


class DashboardTrendItem(BaseModel):
    date: date
    calls_total: int
    calls_answered: int
    calls_unanswered: int
    billed_minutes: float
    total_duration_seconds: int


class DashboardTrendsResponse(BaseModel):
    series: list[DashboardTrendItem]


class DashboardDistributionItem(BaseModel):
    key: str
    label: str
    calls: int
    percentage: float


class DashboardStatusDistributionResponse(BaseModel):
    items: list[DashboardDistributionItem]


class DashboardAgentDistributionItem(BaseModel):
    agent_id: str | None
    agent_name: str
    calls: int
    percentage: float


class DashboardAgentDistributionResponse(BaseModel):
    items: list[DashboardAgentDistributionItem]


class DashboardHeatmapItem(BaseModel):
    day: date
    hour: int = Field(ge=0, le=23)
    calls: int


class DashboardHeatmapResponse(BaseModel):
    matrix: list[DashboardHeatmapItem]


class DashboardRecentCallItem(BaseModel):
    id: str
    started_at: datetime
    duration_seconds: int | None
    billed_minutes: float | None
    agent_name: str
    summary: str | None
    short_summary: str | None
    status: str
    external_provider: str

    model_config = ConfigDict(from_attributes=True)


class DashboardRecentCallsResponse(BaseModel):
    items: list[DashboardRecentCallItem]
    page: int
    page_size: int
    total: int
