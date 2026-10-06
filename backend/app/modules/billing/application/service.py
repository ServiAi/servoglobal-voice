from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.modules.billing.application.ports import TenantAccountPort, UsageMeterPort
from app.modules.billing.contracts import (
    BillingPlanInput,
    BillingPlanView,
    ProviderSavingsView,
    SavingsComparisonView,
    TenantUsageSummaryView,
    TenantUsageView,
    UsageAlertView,
)
from app.modules.billing.domain.errors import (
    BillingTenantNotFoundError,
    InvalidBillingPlanError,
    MinutePackageExhaustedError,
    TenantInactiveError,
)
from app.modules.billing.domain.plans import PLAN_WEB_CONVERSION, decimal, normalize_plan, quantize
from app.modules.billing.domain.pricing import savings
from app.modules.billing.domain.usage import (
    DEFAULT_ALERT_THRESHOLDS,
    STATUS_LIMIT_REACHED,
    STATUS_NORMAL,
    STATUS_OVER_LIMIT,
    STATUS_SUSPENDED_USAGE_LIMIT,
    cost,
    reached_alert_thresholds,
    status_for_usage,
)
from app.modules.billing.infrastructure.models import (
    ExternalProviderPricing,
    TenantBillingPlan,
    TenantUsageAlert,
)

DEFAULT_BILLING_PERIOD_DAYS = 30
ALERT_SPECS = (
    (Decimal("80"), "warning_80", "Tenant usage reached 80% of the minute package."),
    (Decimal("90"), "warning_90", "Tenant usage reached 90% of the minute package."),
    (Decimal("100"), "limit_reached", "Tenant minute package exhausted."),
)
DEFAULT_PROVIDER_PRICING = [
    {"provider_key": "retell", "provider_name": "Retell", "provider_price_per_minute_usd": Decimal("0.1100"), "price_min_per_minute_usd": Decimal("0.0700"), "price_max_per_minute_usd": Decimal("0.3100"), "price_source": "official_estimator", "source_url": "https://www.retellai.com/pricing", "notes": "Official calculator default; pay-as-you-go range is 0.07-0.31 USD/min."},
    {"provider_key": "vapi", "provider_name": "Vapi", "provider_price_per_minute_usd": Decimal("0.0500"), "price_min_per_minute_usd": None, "price_max_per_minute_usd": None, "price_source": "official_base_excludes_provider_costs", "source_url": "https://vapi.ai/pricing", "notes": "Hosting cost only; STT, LLM and TTS provider costs are extra."},
    {"provider_key": "dapta", "provider_name": "Dapta", "provider_price_per_minute_usd": Decimal("0.3300"), "price_min_per_minute_usd": None, "price_max_per_minute_usd": None, "price_source": "official_derived_credits", "source_url": "https://dapta.ai/pricing-2/", "notes": "Derived from Pro plan 99 USD / 100k credits and 333 credits per effective call minute."},
    {"provider_key": "openai_realtime", "provider_name": "OpenAI Realtime", "provider_price_per_minute_usd": Decimal("0.0960"), "price_min_per_minute_usd": None, "price_max_per_minute_usd": None, "price_source": "official_token_estimate", "source_url": "https://platform.openai.com/docs/models/gpt-realtime", "notes": "Assumes 1 minute user audio input plus 1 minute assistant audio output on gpt-realtime."},
    {"provider_key": "gemini_live_api", "provider_name": "Gemini Realtime / Google Live API", "provider_price_per_minute_usd": Decimal("0.0225"), "price_min_per_minute_usd": None, "price_max_per_minute_usd": None, "price_source": "official_token_estimate", "source_url": "https://ai.google.dev/gemini-api/docs/pricing", "notes": "Assumes Gemini 2.5 Flash Native Audio input and output audio for one minute each."},
    {"provider_key": "custom", "provider_name": "Otros / Custom", "provider_price_per_minute_usd": None, "price_min_per_minute_usd": None, "price_max_per_minute_usd": None, "price_source": "manual", "source_url": None, "notes": "Configure manually for provider-specific contracts."},
]


class BillingService:
    def __init__(self, db, usage_meter: UsageMeterPort, tenants: TenantAccountPort) -> None:
        self.db = db
        self.usage_meter = usage_meter
        self.tenants = tenants

    def create_default_plan(self, tenant_id: str, plan: BillingPlanInput | None = None) -> TenantBillingPlan:
        return self._create_plan(tenant_id, plan)

    def ensure_plan(self, tenant_id: str) -> TenantBillingPlan:
        plan = self.db.scalar(select(TenantBillingPlan).where(TenantBillingPlan.tenant_id == tenant_id))
        if plan is not None:
            return plan
        try:
            with self.db.begin_nested():
                plan = self._new_plan(tenant_id, None)
                self.db.add(plan)
                self.db.flush()
            return plan
        except IntegrityError as exc:
            if not self._is_plan_unique_conflict(exc):
                raise
            winner = self.db.scalar(select(TenantBillingPlan).where(TenantBillingPlan.tenant_id == tenant_id))
            if winner is None:
                raise
            return winner

    def _create_plan(self, tenant_id: str, payload: BillingPlanInput | None) -> TenantBillingPlan:
        plan = self._new_plan(tenant_id, payload)
        self.db.add(plan)
        self.db.flush()
        return plan

    @staticmethod
    def _is_plan_unique_conflict(exc: IntegrityError) -> bool:
        original = exc.orig
        name = getattr(getattr(original, "diag", None), "constraint_name", None)
        if name:
            return name == "uq_tenant_billing_plans_tenant_id"
        text = str(original).lower()
        return "unique constraint failed: tenant_billing_plans.tenant_id" in text

    @staticmethod
    def _new_plan(tenant_id: str, payload: BillingPlanInput | None) -> TenantBillingPlan:
        key = payload.plan_key if payload else PLAN_WEB_CONVERSION
        name, minutes, price = normalize_plan(
            key,
            payload.included_minutes if payload else None,
            payload.price_per_minute_usd if payload else None,
        )
        now = datetime.now(UTC)
        return TenantBillingPlan(
            tenant_id=tenant_id,
            plan_key=key,
            plan_name=name,
            included_minutes=minutes,
            price_per_minute_usd=price,
            usage_status=STATUS_NORMAL,
            billing_period_start=now,
            billing_period_end=now + timedelta(days=DEFAULT_BILLING_PERIOD_DAYS),
            alert_thresholds=list(DEFAULT_ALERT_THRESHOLDS),
        )

    def update_plan(self, tenant_id: str, payload: BillingPlanInput) -> TenantUsageView:
        tenant = self._tenant(tenant_id)
        plan = self.ensure_plan(tenant_id)
        plan = self.db.scalar(
            select(TenantBillingPlan).where(TenantBillingPlan.id == plan.id).with_for_update()
        )
        name, minutes, price = normalize_plan(payload.plan_key, payload.included_minutes, payload.price_per_minute_usd)
        plan.plan_key, plan.plan_name = payload.plan_key, name
        plan.included_minutes, plan.price_per_minute_usd = minutes, price
        plan.alert_thresholds = list(DEFAULT_ALERT_THRESHOLDS)
        return self._refresh(tenant, plan, persist_alerts=True)

    def get_usage(self, tenant_id: str, *, persist_alerts: bool = True, commit: bool = True) -> TenantUsageView:
        return self._refresh(self._tenant(tenant_id), persist_alerts=persist_alerts, commit=commit)

    def _tenant(self, tenant_id: str):
        tenant = self.tenants.get(tenant_id)
        if tenant is None:
            raise BillingTenantNotFoundError(f"Tenant '{tenant_id}' not found")
        return tenant

    def _refresh(self, tenant, plan: TenantBillingPlan | None = None, *, persist_alerts: bool, commit: bool = True) -> TenantUsageView:
        plan = plan or self.ensure_plan(tenant.id)
        plan = self.db.scalar(select(TenantBillingPlan).where(TenantBillingPlan.id == plan.id).with_for_update())
        used = quantize(decimal(self.usage_meter.billed_minutes(tenant.id, plan.billing_period_start, plan.billing_period_end)), "0.01")
        percent = used / plan.included_minutes * Decimal("100") if plan.included_minutes > 0 else Decimal("0")
        remaining = plan.included_minutes - used
        amount = cost(used, plan.price_per_minute_usd)
        calculated = status_for_usage(percent)
        if calculated in {STATUS_LIMIT_REACHED, STATUS_OVER_LIMIT}:
            plan.usage_status = STATUS_SUSPENDED_USAGE_LIMIT
            self.tenants.set_usage_suspension(tenant.id, True, commit=False)
        else:
            plan.usage_status = calculated
            if tenant.status == STATUS_SUSPENDED_USAGE_LIMIT:
                self.tenants.set_usage_suspension(tenant.id, False, commit=False)
        plan.last_usage_recalculated_at = datetime.now(UTC)
        if persist_alerts:
            self._persist_alerts(tenant.id, plan, percent)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(plan)
        alerts = self.db.scalars(
            select(TenantUsageAlert)
            .where(TenantUsageAlert.tenant_id == tenant.id, TenantUsageAlert.billing_period_start == plan.billing_period_start)
            .order_by(TenantUsageAlert.threshold_percent.asc())
        ).all()
        return TenantUsageView(
            tenant_id=tenant.id,
            plan=self._plan_view(plan),
            minutes_used=quantize(used, "0.01"),
            minutes_remaining=quantize(remaining, "0.01"),
            usage_percent=quantize(percent, "0.01"),
            amount_spent_usd=quantize(amount, "0.01"),
            usage_status=plan.usage_status,
            alerts=tuple(self._alert_view(a) for a in alerts),
        )

    def _persist_alerts(self, tenant_id: str, plan: TenantBillingPlan, percent: Decimal) -> None:
        existing = set(self.db.scalars(select(TenantUsageAlert.alert_type).where(
            TenantUsageAlert.tenant_id == tenant_id,
            TenantUsageAlert.billing_period_start == plan.billing_period_start,
        )).all())
        reached = set(reached_alert_thresholds(percent))
        for threshold, alert_type, message in ALERT_SPECS:
            if threshold in reached and alert_type not in existing:
                self.db.add(TenantUsageAlert(
                    tenant_id=tenant_id,
                    billing_plan_id=plan.id,
                    alert_type=alert_type,
                    threshold_percent=threshold,
                    billing_period_start=plan.billing_period_start,
                    message=message,
                    status="active",
                ))

    def list_usage_alerts(self, tenant_id: str | None = None) -> tuple[UsageAlertView, ...]:
        statement = select(TenantUsageAlert).order_by(TenantUsageAlert.created_at.desc())
        if tenant_id is not None:
            statement = statement.where(TenantUsageAlert.tenant_id == tenant_id)
        return tuple(self._alert_view(a) for a in self.db.scalars(statement).all())

    def list_usage_summary(self) -> tuple[TenantUsageSummaryView, ...]:
        summaries = []
        for tenant in self.tenants.list_tenants():
            usage = self._refresh(tenant, persist_alerts=True)
            summaries.append(TenantUsageSummaryView(
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
            ))
        return tuple(summaries)

    def get_savings_comparison(self, tenant_id: str) -> SavingsComparisonView:
        usage = self.get_usage(tenant_id)
        price = usage.plan.price_per_minute_usd
        serviglobal = cost(usage.minutes_used, price)
        rows = self.db.scalars(select(ExternalProviderPricing).order_by(ExternalProviderPricing.provider_name.asc())).all()
        providers = rows or DEFAULT_PROVIDER_PRICING
        views = []
        for provider in providers:
            value = provider.get if isinstance(provider, dict) else lambda key: getattr(provider, key)
            provider_price = value("provider_price_per_minute_usd")
            provider_price = decimal(provider_price) if provider_price is not None else None
            estimate, own_cost, amount, percent = savings(usage.minutes_used, provider_price, price)
            views.append(ProviderSavingsView(
                provider_key=str(value("provider_key")),
                provider_name=str(value("provider_name")),
                provider_price_per_minute_usd=quantize(provider_price, "0.0001") if provider_price is not None else None,
                price_min_per_minute_usd=quantize(decimal(value("price_min_per_minute_usd")), "0.0001") if value("price_min_per_minute_usd") is not None else None,
                price_max_per_minute_usd=quantize(decimal(value("price_max_per_minute_usd")), "0.0001") if value("price_max_per_minute_usd") is not None else None,
                price_source=str(value("price_source")),
                source_url=value("source_url"),
                estimated_cost_usd=quantize(estimate, "0.01") if estimate is not None else None,
                serviglobal_cost_usd=quantize(own_cost, "0.01"),
                estimated_savings_usd=quantize(amount, "0.01") if amount is not None else None,
                estimated_savings_percent=quantize(percent, "0.01") if percent is not None else None,
                notes=value("notes"),
            ))
        return SavingsComparisonView(
            tenant_id,
            quantize(usage.minutes_used, "0.01"),
            quantize(price, "0.0001"),
            quantize(serviglobal, "0.01"),
            tuple(views),
        )

    def ensure_call_allowed_by_slug(self, tenant_slug: str) -> None:
        tenant = self.tenants.get_by_slug(tenant_slug)
        if tenant is None:
            raise BillingTenantNotFoundError("Unable to resolve tenant for call creation")
        usage = self._refresh(tenant, persist_alerts=True)
        if usage.usage_status in {STATUS_LIMIT_REACHED, STATUS_OVER_LIMIT, STATUS_SUSPENDED_USAGE_LIMIT} or usage.minutes_remaining <= 0:
            raise MinutePackageExhaustedError("Tenant minute package exhausted")
        if tenant.status != "active":
            raise TenantInactiveError("Tenant is not active")

    def cleanup_tenant(self, tenant_id: str) -> dict[str, int]:
        from sqlalchemy import delete

        alerts = self.db.execute(delete(TenantUsageAlert).where(TenantUsageAlert.tenant_id == tenant_id))
        plans = self.db.execute(delete(TenantBillingPlan).where(TenantBillingPlan.tenant_id == tenant_id))
        return {"usage_alerts": max(alerts.rowcount or 0, 0), "billing_plans": max(plans.rowcount or 0, 0)}

    @staticmethod
    def _plan_view(plan: TenantBillingPlan) -> BillingPlanView:
        return BillingPlanView(
            tenant_id=plan.tenant_id,
            plan_key=plan.plan_key,
            plan_name=plan.plan_name,
            included_minutes=plan.included_minutes,
            price_per_minute_usd=plan.price_per_minute_usd,
            usage_status=plan.usage_status,
            billing_period_start=plan.billing_period_start,
            billing_period_end=plan.billing_period_end,
            alert_thresholds=tuple(int(value) for value in plan.alert_thresholds),
            last_usage_recalculated_at=plan.last_usage_recalculated_at,
        )

    @staticmethod
    def _alert_view(alert: TenantUsageAlert) -> UsageAlertView:
        return UsageAlertView(
            id=alert.id,
            tenant_id=alert.tenant_id,
            alert_type=alert.alert_type,
            threshold_percent=alert.threshold_percent,
            billing_period_start=alert.billing_period_start,
            message=alert.message,
            status=alert.status,
            created_at=alert.created_at,
        )
