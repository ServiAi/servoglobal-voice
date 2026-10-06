from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.analytics import Call
from app.modules.billing.application.ports import TenantAccountPort, UsageMeterPort
from app.modules.billing.application.service import BillingService
from app.modules.identity.public import IdentityAdminFacade, TenantDirectory, TenantLifecycle


class LegacyAnalyticsUsageMeter:
    """Temporary adapter for call facts until Analytics exposes its public API."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def billed_minutes(self, tenant_id: str, period_start, period_end) -> Decimal:
        total = self.db.scalar(
            select(func.coalesce(func.sum(Call.billed_minutes), 0)).where(
                Call.tenant_id == tenant_id,
                Call.billed_minutes.is_not(None),
                Call.normalized_status != "in_progress",
                Call.started_at >= period_start,
                Call.started_at <= period_end,
            )
        )
        return Decimal(str(total or 0))


class IdentityTenantAccountAdapter:
    def __init__(self, db: Session) -> None:
        self.directory = TenantDirectory(db)
        self.admin = IdentityAdminFacade(db)
        self.lifecycle = TenantLifecycle(db)

    def get(self, tenant_id: str):
        return self.directory.get(tenant_id)

    def get_by_slug(self, slug: str):
        return self.directory.get_by_slug(slug)

    def list_tenants(self):
        return self.admin.list_tenants()

    def set_usage_suspension(self, tenant_id: str, suspended: bool, *, commit: bool) -> None:
        self.lifecycle.set_usage_suspension(tenant_id, suspended, commit=commit)


def build_billing_service(db: Session) -> BillingService:
    return BillingService(
        db,
        usage_meter=LegacyAnalyticsUsageMeter(db),
        tenants=IdentityTenantAccountAdapter(db),
    )
