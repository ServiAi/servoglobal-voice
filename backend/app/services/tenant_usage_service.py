from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.analytics import Call
from app.models.billing import ExternalProviderPricing, TenantBillingPlan, TenantUsageAlert
from app.models.identity import Tenant
from app.schemas.billing import (
    SavingsComparisonProviderResponse,
    TenantPlanRequest,
    TenantPlanResponse,
    TenantSavingsComparisonResponse,
    TenantUsageAlertResponse,
    TenantUsageResponse,
    TenantUsageSummaryResponse,
)


PLAN_WEB_CONVERSION = "web_conversion"
PLAN_VOICE_CLOUD_PBX = "voice_cloud_pbx"
PLAN_ENTERPRISE = "enterprise"
STATUS_NORMAL = "normal"
STATUS_APPROACHING_LIMIT = "approaching_limit"
STATUS_LIMIT_REACHED = "limit_reached"
STATUS_OVER_LIMIT = "over_limit"
STATUS_SUSPENDED_USAGE_LIMIT = "suspended_usage_limit"
TENANT_ACTIVE = "active"

DEFAULT_ALERT_THRESHOLDS = [80, 90, 100]
DEFAULT_BILLING_PERIOD_DAYS = 30


@dataclass(frozen=True)
class PlanDefinition:
    key: str
    name: str
    included_minutes: Decimal
    price_per_minute_usd: Decimal


PLAN_DEFINITIONS = {
    PLAN_WEB_CONVERSION: PlanDefinition(
        key=PLAN_WEB_CONVERSION,
        name="Plan Web Conversion",
        included_minutes=Decimal("2000.00"),
        price_per_minute_usd=Decimal("0.1600"),
    ),
    PLAN_VOICE_CLOUD_PBX: PlanDefinition(
        key=PLAN_VOICE_CLOUD_PBX,
        name="Plan Voice Cloud / PBX",
        included_minutes=Decimal("2000.00"),
        price_per_minute_usd=Decimal("0.1800"),
    ),
}

DEFAULT_PROVIDER_PRICING: list[dict[str, Any]] = [
    {
        "provider_key": "retell",
        "provider_name": "Retell",
        "provider_price_per_minute_usd": Decimal("0.1100"),
        "price_min_per_minute_usd": Decimal("0.0700"),
        "price_max_per_minute_usd": Decimal("0.3100"),
        "price_source": "official_estimator",
        "source_url": "https://www.retellai.com/pricing",
        "notes": "Official calculator default; pay-as-you-go range is 0.07-0.31 USD/min.",
    },
    {
        "provider_key": "vapi",
        "provider_name": "Vapi",
        "provider_price_per_minute_usd": Decimal("0.0500"),
        "price_min_per_minute_usd": None,
        "price_max_per_minute_usd": None,
        "price_source": "official_base_excludes_provider_costs",
        "source_url": "https://vapi.ai/pricing",
        "notes": "Hosting cost only; STT, LLM and TTS provider costs are extra.",
    },
    {
        "provider_key": "dapta",
        "provider_name": "Dapta",
        "provider_price_per_minute_usd": Decimal("0.3300"),
        "price_min_per_minute_usd": None,
        "price_max_per_minute_usd": None,
        "price_source": "official_derived_credits",
        "source_url": "https://dapta.ai/pricing-2/",
        "notes": "Derived from Pro plan 99 USD / 100k credits and 333 credits per effective call minute.",
    },
    {
        "provider_key": "openai_realtime",
        "provider_name": "OpenAI Realtime",
        "provider_price_per_minute_usd": Decimal("0.0960"),
        "price_min_per_minute_usd": None,
        "price_max_per_minute_usd": None,
        "price_source": "official_token_estimate",
        "source_url": "https://platform.openai.com/docs/models/gpt-realtime",
        "notes": "Assumes 1 minute user audio input plus 1 minute assistant audio output on gpt-realtime.",
    },
    {
        "provider_key": "gemini_live_api",
        "provider_name": "Gemini Realtime / Google Live API",
        "provider_price_per_minute_usd": Decimal("0.0225"),
        "price_min_per_minute_usd": None,
        "price_max_per_minute_usd": None,
        "price_source": "official_token_estimate",
        "source_url": "https://ai.google.dev/gemini-api/docs/pricing",
        "notes": "Assumes Gemini 2.5 Flash Native Audio input and output audio for one minute each.",
    },
    {
        "provider_key": "custom",
        "provider_name": "Otros / Custom",
        "provider_price_per_minute_usd": None,
        "price_min_per_minute_usd": None,
        "price_max_per_minute_usd": None,
        "price_source": "manual",
        "source_url": None,
        "notes": "Configure manually for provider-specific contracts.",
    },
]


class TenantUsageService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_plan_for_tenant(
        self,
        tenant: Tenant,
        plan_request: TenantPlanRequest | None = None,
        *,
        commit: bool = False,
    ) -> TenantBillingPlan:
        plan_key = plan_request.plan_key if plan_request else PLAN_WEB_CONVERSION
        included_minutes = plan_request.included_minutes if plan_request else None
        price = plan_request.price_per_minute_usd if plan_request else None
        plan_name, normalized_minutes, normalized_price = self._normalize_plan(
            plan_key,
            included_minutes,
            price,
        )
        now = datetime.now(UTC)
        plan = TenantBillingPlan(
            tenant_id=tenant.id,
            plan_key=plan_key,
            plan_name=plan_name,
            included_minutes=normalized_minutes,
            price_per_minute_usd=normalized_price,
            usage_status=STATUS_NORMAL,
            billing_period_start=now,
            billing_period_end=now + timedelta(days=DEFAULT_BILLING_PERIOD_DAYS),
            alert_thresholds=list(DEFAULT_ALERT_THRESHOLDS),
        )
        self.db.add(plan)
        if commit:
            self.db.commit()
            self.db.refresh(plan)
        else:
            self.db.flush()
        return plan

    def ensure_plan(self, tenant: Tenant) -> TenantBillingPlan:
        plan = self.db.scalar(
            select(TenantBillingPlan).where(TenantBillingPlan.tenant_id == tenant.id)
        )
        if plan is not None:
            return plan
        return self.create_plan_for_tenant(tenant, commit=True)

    def update_plan(self, tenant_id: str, payload: TenantPlanRequest) -> TenantUsageResponse:
        tenant = self._get_tenant(tenant_id)
        plan = self.ensure_plan(tenant)
        plan_name, included_minutes, price = self._normalize_plan(
            payload.plan_key,
            payload.included_minutes,
            payload.price_per_minute_usd,
        )
        plan.plan_key = payload.plan_key
        plan.plan_name = plan_name
        plan.included_minutes = included_minutes
        plan.price_per_minute_usd = price
        plan.alert_thresholds = list(DEFAULT_ALERT_THRESHOLDS)
        return self.refresh_usage_state(tenant, persist_alerts=True)

    def get_usage(self, tenant: Tenant, *, persist_alerts: bool = True) -> TenantUsageResponse:
        return self.refresh_usage_state(tenant, persist_alerts=persist_alerts)

    def get_savings_comparison(self, tenant: Tenant) -> TenantSavingsComparisonResponse:
        usage = self.refresh_usage_state(tenant, persist_alerts=True)
        plan = usage.plan
        minutes_used = self._decimal(usage.minutes_used)
        serviglobal_price = self._decimal(plan.price_per_minute_usd)
        serviglobal_cost = minutes_used * serviglobal_price

        providers = []
        for provider in self._provider_pricing_rows():
            provider_price = self._provider_decimal(provider, "provider_price_per_minute_usd")
            estimated_cost = provider_price * minutes_used if provider_price is not None else None
            savings = estimated_cost - serviglobal_cost if estimated_cost is not None else None
            savings_percent = (
                (savings / estimated_cost * Decimal("100"))
                if savings is not None and estimated_cost and estimated_cost > Decimal("0")
                else None
            )
            providers.append(
                SavingsComparisonProviderResponse(
                    provider_key=str(self._provider_value(provider, "provider_key")),
                    provider_name=str(self._provider_value(provider, "provider_name")),
                    provider_price_per_minute_usd=self._float_or_none(provider_price, "0.0001"),
                    price_min_per_minute_usd=self._float_or_none(
                        self._provider_decimal(provider, "price_min_per_minute_usd"),
                        "0.0001",
                    ),
                    price_max_per_minute_usd=self._float_or_none(
                        self._provider_decimal(provider, "price_max_per_minute_usd"),
                        "0.0001",
                    ),
                    price_source=str(self._provider_value(provider, "price_source")),
                    source_url=self._provider_value(provider, "source_url"),
                    estimated_cost_usd=self._float_or_none(estimated_cost, "0.01"),
                    serviglobal_cost_usd=self._float(serviglobal_cost, "0.01"),
                    estimated_savings_usd=self._float_or_none(savings, "0.01"),
                    estimated_savings_percent=self._float_or_none(savings_percent, "0.01"),
                    notes=self._provider_value(provider, "notes"),
                )
            )

        return TenantSavingsComparisonResponse(
            tenant_id=tenant.id,
            minutes_used=self._float(minutes_used, "0.01"),
            serviglobal_price_per_minute_usd=self._float(serviglobal_price, "0.0001"),
            serviglobal_cost_usd=self._float(serviglobal_cost, "0.01"),
            providers=providers,
        )

    def list_usage_alerts(self, tenant_id: str | None = None) -> list[TenantUsageAlertResponse]:
        conditions = []
        if tenant_id is not None:
            conditions.append(TenantUsageAlert.tenant_id == tenant_id)
        statement = select(TenantUsageAlert).order_by(TenantUsageAlert.created_at.desc())
        if conditions:
            statement = statement.where(and_(*conditions))
        alerts = self.db.scalars(statement).all()
        return [self._alert_response(alert) for alert in alerts]

    def list_usage_summary(self) -> list[TenantUsageSummaryResponse]:
        tenants = self.db.scalars(select(Tenant).order_by(Tenant.created_at.desc())).all()
        summaries = []
        for tenant in tenants:
            usage = self.refresh_usage_state(tenant, persist_alerts=True)
            summaries.append(
                TenantUsageSummaryResponse(
                    tenant_id=tenant.id,
                    tenant_name=tenant.name,
                    tenant_slug=tenant.slug,
                    tenant_status=tenant.status,
                    plan_key=usage.plan.plan_key,
                    plan_name=usage.plan.plan_name,
                    included_minutes=usage.plan.included_minutes,
                    minutes_used=usage.minutes_used,
                    usage_percent=usage.usage_percent,
                    usage_status=usage.usage_status,
                )
            )
        return summaries

    def ensure_tenant_can_start_call_by_slug(self, tenant_slug: str) -> None:
        tenant = self.db.scalar(select(Tenant).where(Tenant.slug == tenant_slug))
        if tenant is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unable to resolve tenant for call creation",
            )
        usage = self.refresh_usage_state(tenant, persist_alerts=True)
        if usage.usage_status in {
            STATUS_LIMIT_REACHED,
            STATUS_OVER_LIMIT,
            STATUS_SUSPENDED_USAGE_LIMIT,
        } or usage.minutes_remaining <= 0:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Tenant minute package exhausted",
            )
        if tenant.status != TENANT_ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant is not active",
            )

    def refresh_usage_state(self, tenant: Tenant, *, persist_alerts: bool) -> TenantUsageResponse:
        plan = self.ensure_plan(tenant)
        minutes_used = self._calculate_minutes_used(tenant.id, plan)
        usage_percent = (
            (minutes_used / plan.included_minutes * Decimal("100"))
            if plan.included_minutes > Decimal("0")
            else Decimal("0")
        )
        minutes_remaining = plan.included_minutes - minutes_used
        amount_spent = minutes_used * plan.price_per_minute_usd
        calculated_status = self._status_for_usage(usage_percent)

        if calculated_status in {STATUS_LIMIT_REACHED, STATUS_OVER_LIMIT}:
            plan.usage_status = STATUS_SUSPENDED_USAGE_LIMIT
            tenant.status = STATUS_SUSPENDED_USAGE_LIMIT
        else:
            plan.usage_status = calculated_status
            if tenant.status == STATUS_SUSPENDED_USAGE_LIMIT:
                tenant.status = TENANT_ACTIVE

        plan.last_usage_recalculated_at = datetime.now(UTC)
        if persist_alerts:
            self._persist_alerts(tenant, plan, usage_percent)
        self.db.commit()
        self.db.refresh(plan)
        self.db.refresh(tenant)

        alerts = self.db.scalars(
            select(TenantUsageAlert)
            .where(
                TenantUsageAlert.tenant_id == tenant.id,
                TenantUsageAlert.billing_period_start == plan.billing_period_start,
            )
            .order_by(TenantUsageAlert.threshold_percent.asc())
        ).all()
        return TenantUsageResponse(
            tenant_id=tenant.id,
            plan=self._plan_response(plan),
            minutes_used=self._float(minutes_used, "0.01"),
            minutes_remaining=self._float(minutes_remaining, "0.01"),
            usage_percent=self._float(usage_percent, "0.01"),
            amount_spent_usd=self._float(amount_spent, "0.01"),
            usage_status=plan.usage_status,
            alerts=[self._alert_response(alert) for alert in alerts],
        )

    def _normalize_plan(
        self,
        plan_key: str,
        included_minutes: Decimal | None,
        price_per_minute_usd: Decimal | None,
    ) -> tuple[str, Decimal, Decimal]:
        if plan_key in PLAN_DEFINITIONS:
            definition = PLAN_DEFINITIONS[plan_key]
            return definition.name, definition.included_minutes, definition.price_per_minute_usd
        if plan_key != PLAN_ENTERPRISE:
            raise ValueError(f"Unknown plan_key '{plan_key}'")

        minutes = self._decimal(included_minutes)
        price = self._decimal(price_per_minute_usd)
        if minutes < Decimal("2000"):
            raise ValueError("Enterprise included_minutes must be greater than or equal to 2000")
        if price < Decimal("0.14") or price > Decimal("0.15"):
            raise ValueError("Enterprise price_per_minute_usd must be between 0.14 and 0.15")
        return "Enterprise", self._quantize(minutes, "0.01"), self._quantize(price, "0.0001")

    def _get_tenant(self, tenant_id: str) -> Tenant:
        tenant = self.db.get(Tenant, tenant_id)
        if tenant is None:
            raise ValueError(f"Tenant '{tenant_id}' not found")
        return tenant

    def _calculate_minutes_used(self, tenant_id: str, plan: TenantBillingPlan) -> Decimal:
        total = self.db.scalar(
            select(func.coalesce(func.sum(Call.billed_minutes), 0)).where(
                Call.tenant_id == tenant_id,
                Call.billed_minutes.is_not(None),
                Call.normalized_status != "in_progress",
                Call.started_at >= plan.billing_period_start,
                Call.started_at <= plan.billing_period_end,
            )
        )
        return self._quantize(self._decimal(total), "0.01")

    def _status_for_usage(self, usage_percent: Decimal) -> str:
        if usage_percent > Decimal("100"):
            return STATUS_OVER_LIMIT
        if usage_percent >= Decimal("100"):
            return STATUS_LIMIT_REACHED
        if usage_percent >= Decimal("80"):
            return STATUS_APPROACHING_LIMIT
        return STATUS_NORMAL

    def _persist_alerts(
        self,
        tenant: Tenant,
        plan: TenantBillingPlan,
        usage_percent: Decimal,
    ) -> None:
        alert_specs = [
            (Decimal("80"), "warning_80", "Tenant usage reached 80% of the minute package."),
            (Decimal("90"), "warning_90", "Tenant usage reached 90% of the minute package."),
            (Decimal("100"), "limit_reached", "Tenant minute package exhausted."),
        ]
        existing = {
            alert.alert_type
            for alert in self.db.scalars(
                select(TenantUsageAlert).where(
                    TenantUsageAlert.tenant_id == tenant.id,
                    TenantUsageAlert.billing_period_start == plan.billing_period_start,
                )
            ).all()
        }
        for threshold, alert_type, message in alert_specs:
            if usage_percent < threshold or alert_type in existing:
                continue
            self.db.add(
                TenantUsageAlert(
                    tenant_id=tenant.id,
                    billing_plan_id=plan.id,
                    alert_type=alert_type,
                    threshold_percent=threshold,
                    billing_period_start=plan.billing_period_start,
                    message=message,
                    status="active",
                )
            )

    def _provider_pricing_rows(self) -> list[ExternalProviderPricing | dict[str, Any]]:
        rows = self.db.scalars(
            select(ExternalProviderPricing).order_by(ExternalProviderPricing.provider_name.asc())
        ).all()
        return list(rows) if rows else DEFAULT_PROVIDER_PRICING

    def _plan_response(self, plan: TenantBillingPlan) -> TenantPlanResponse:
        return TenantPlanResponse(
            tenant_id=plan.tenant_id,
            plan_key=plan.plan_key,
            plan_name=plan.plan_name,
            included_minutes=self._float(plan.included_minutes, "0.01"),
            price_per_minute_usd=self._float(plan.price_per_minute_usd, "0.0001"),
            usage_status=plan.usage_status,
            billing_period_start=plan.billing_period_start,
            billing_period_end=plan.billing_period_end,
            alert_thresholds=[int(value) for value in plan.alert_thresholds],
            last_usage_recalculated_at=plan.last_usage_recalculated_at,
        )

    def _alert_response(self, alert: TenantUsageAlert) -> TenantUsageAlertResponse:
        return TenantUsageAlertResponse(
            id=alert.id,
            tenant_id=alert.tenant_id,
            alert_type=alert.alert_type,
            threshold_percent=self._float(alert.threshold_percent, "0.01"),
            billing_period_start=alert.billing_period_start,
            message=alert.message,
            status=alert.status,
            created_at=alert.created_at,
        )

    def _provider_value(
        self,
        provider: ExternalProviderPricing | dict[str, Any],
        key: str,
    ) -> Any:
        if isinstance(provider, dict):
            return provider.get(key)
        return getattr(provider, key)

    def _provider_decimal(
        self,
        provider: ExternalProviderPricing | dict[str, Any],
        key: str,
    ) -> Decimal | None:
        value = self._provider_value(provider, key)
        if value is None:
            return None
        return self._decimal(value)

    def _decimal(self, value: Decimal | int | float | str | None) -> Decimal:
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    def _float(self, value: Decimal | int | float | str | None, places: str) -> float:
        return float(self._quantize(self._decimal(value), places))

    def _float_or_none(self, value: Decimal | int | float | str | None, places: str) -> float | None:
        if value is None:
            return None
        return self._float(value, places)

    def _quantize(self, value: Decimal, places: str) -> Decimal:
        return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)
