from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


PLAN_KEYS = ("web_conversion", "voice_cloud_pbx", "enterprise")


class TenantPlanRequest(BaseModel):
    plan_key: str = Field(..., pattern="^(web_conversion|voice_cloud_pbx|enterprise)$")
    included_minutes: Decimal | None = Field(default=None)
    price_per_minute_usd: Decimal | None = Field(default=None)

    @model_validator(mode="after")
    def validate_enterprise_values(self) -> "TenantPlanRequest":
        if self.plan_key != "enterprise":
            return self
        if self.included_minutes is None or self.included_minutes < Decimal("2000"):
            raise ValueError("enterprise included_minutes must be greater than or equal to 2000")
        if (
            self.price_per_minute_usd is None
            or self.price_per_minute_usd < Decimal("0.14")
            or self.price_per_minute_usd > Decimal("0.15")
        ):
            raise ValueError("enterprise price_per_minute_usd must be between 0.14 and 0.15")
        return self


class TenantPlanResponse(BaseModel):
    tenant_id: str
    plan_key: str
    plan_name: str
    included_minutes: float
    price_per_minute_usd: float
    usage_status: str
    billing_period_start: datetime
    billing_period_end: datetime
    alert_thresholds: list[int]
    last_usage_recalculated_at: datetime | None = None


class TenantUsageAlertResponse(BaseModel):
    id: str
    tenant_id: str
    alert_type: str
    threshold_percent: float
    billing_period_start: datetime
    message: str
    status: str
    created_at: datetime


class TenantUsageResponse(BaseModel):
    tenant_id: str
    plan: TenantPlanResponse
    minutes_used: float
    minutes_remaining: float
    usage_percent: float
    amount_spent_usd: float
    usage_status: str
    alerts: list[TenantUsageAlertResponse] = Field(default_factory=list)


class SavingsComparisonProviderResponse(BaseModel):
    provider_key: str
    provider_name: str
    provider_price_per_minute_usd: float | None
    price_min_per_minute_usd: float | None = None
    price_max_per_minute_usd: float | None = None
    price_source: str
    source_url: str | None = None
    estimated_cost_usd: float | None
    serviglobal_cost_usd: float
    estimated_savings_usd: float | None
    estimated_savings_percent: float | None
    notes: str | None = None


class TenantSavingsComparisonResponse(BaseModel):
    tenant_id: str
    minutes_used: float
    serviglobal_price_per_minute_usd: float
    serviglobal_cost_usd: float
    providers: list[SavingsComparisonProviderResponse]


class TenantUsageSummaryResponse(BaseModel):
    tenant_id: str
    tenant_name: str
    tenant_slug: str
    tenant_status: str
    plan_key: str
    plan_name: str
    included_minutes: float
    minutes_used: float
    usage_percent: float
    usage_status: str
