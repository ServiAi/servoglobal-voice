from sqlalchemy.orm import Session

from app.modules.analytics.public import AnalyticsUsageFacts
from app.modules.billing.application.service import BillingService
from app.modules.identity.public import (
    IdentityAdminFacade,
    TenantDirectory,
    TenantLifecycle,
)


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
        usage_meter=AnalyticsUsageFacts(db),
        tenants=IdentityTenantAccountAdapter(db),
    )
