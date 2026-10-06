"""Import-light public Billing facades and data contracts."""

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
    BillingError,
    BillingStateConflictError,
    BillingTenantNotFoundError,
    InvalidBillingPlanError,
    MinutePackageExhaustedError,
    TenantInactiveError,
)


def _service(db):
    from app.modules.billing.wiring import build_billing_service

    return build_billing_service(db)


class BillingFacade:
    def __init__(self, db: object) -> None:
        self.db = db

    def get_usage(
        self, tenant_id: str, *, persist_alerts: bool = True, commit: bool = True
    ) -> TenantUsageView:
        return _service(self.db).get_usage(tenant_id, persist_alerts=persist_alerts, commit=commit)

    def get_savings_comparison(self, tenant_id: str) -> SavingsComparisonView:
        return _service(self.db).get_savings_comparison(tenant_id)

    def list_usage_alerts(self, tenant_id: str | None = None) -> tuple[UsageAlertView, ...]:
        return _service(self.db).list_usage_alerts(tenant_id)

    def list_usage_summary(self) -> tuple[TenantUsageSummaryView, ...]:
        return _service(self.db).list_usage_summary()

    def update_plan(self, tenant_id: str, plan: BillingPlanInput) -> TenantUsageView:
        return _service(self.db).update_plan(tenant_id, plan)


class BillingAccessGate:
    def __init__(self, db: object) -> None:
        self.db = db

    def ensure_call_allowed_by_slug(self, tenant_slug: str) -> None:
        _service(self.db).ensure_call_allowed_by_slug(tenant_slug)


class BillingOnboardingFacade:
    """Identity participant; all writes flush into the caller's transaction."""

    def __init__(self, db: object) -> None:
        self.db = db

    def create_default_plan(self, tenant_id: str, plan: BillingPlanInput | None = None) -> None:
        _service(self.db).create_default_plan(tenant_id, plan)

    def tenant_usage_snapshot(self, tenant_id: str) -> TenantUsageView:
        return _service(self.db).get_usage(tenant_id, persist_alerts=False, commit=False)

    def cleanup_tenant(self, tenant_id: str) -> dict[str, int]:
        return _service(self.db).cleanup_tenant(tenant_id)


__all__ = [
    "BillingAccessGate",
    "BillingError",
    "BillingFacade",
    "BillingOnboardingFacade",
    "BillingPlanInput",
    "BillingPlanView",
    "BillingStateConflictError",
    "BillingTenantNotFoundError",
    "InvalidBillingPlanError",
    "MinutePackageExhaustedError",
    "ProviderSavingsView",
    "SavingsComparisonView",
    "TenantInactiveError",
    "TenantUsageSummaryView",
    "TenantUsageView",
    "UsageAlertView",
]
