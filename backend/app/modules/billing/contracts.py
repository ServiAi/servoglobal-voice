from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class BillingPlanInput:
    plan_key: str
    included_minutes: Decimal | None = None
    price_per_minute_usd: Decimal | None = None


@dataclass(frozen=True)
class BillingPlanView:
    tenant_id: str
    plan_key: str
    plan_name: str
    included_minutes: Decimal
    price_per_minute_usd: Decimal
    usage_status: str
    billing_period_start: datetime
    billing_period_end: datetime
    alert_thresholds: tuple[int, ...]
    last_usage_recalculated_at: datetime | None


@dataclass(frozen=True)
class UsageAlertView:
    id: str
    tenant_id: str
    alert_type: str
    threshold_percent: Decimal
    billing_period_start: datetime
    message: str
    status: str
    created_at: datetime


@dataclass(frozen=True)
class TenantUsageView:
    tenant_id: str
    plan: BillingPlanView
    minutes_used: Decimal
    minutes_remaining: Decimal
    usage_percent: Decimal
    amount_spent_usd: Decimal
    usage_status: str
    alerts: tuple[UsageAlertView, ...]


@dataclass(frozen=True)
class ProviderSavingsView:
    provider_key: str
    provider_name: str
    provider_price_per_minute_usd: Decimal | None
    price_min_per_minute_usd: Decimal | None
    price_max_per_minute_usd: Decimal | None
    price_source: str
    source_url: str | None
    estimated_cost_usd: Decimal | None
    serviglobal_cost_usd: Decimal
    estimated_savings_usd: Decimal | None
    estimated_savings_percent: Decimal | None
    notes: str | None


@dataclass(frozen=True)
class SavingsComparisonView:
    tenant_id: str
    minutes_used: Decimal
    serviglobal_price_per_minute_usd: Decimal
    serviglobal_cost_usd: Decimal
    providers: tuple[ProviderSavingsView, ...]


@dataclass(frozen=True)
class TenantUsageSummaryView:
    tenant_id: str
    tenant_name: str
    tenant_slug: str
    tenant_status: str
    plan_key: str
    plan_name: str
    included_minutes: Decimal
    minutes_used: Decimal
    usage_percent: Decimal
    usage_status: str
