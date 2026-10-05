from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.identity.infrastructure.models import Tenant
from app.modules.identity.public import TenantView


class TenantService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def set_usage_suspension(
        self, tenant_id: str, suspended: bool, *, commit: bool = True
    ) -> TenantView:
        tenant = self.db.scalar(
            select(Tenant).where(Tenant.id == tenant_id).with_for_update()
        )
        if tenant is None:
            raise LookupError(f"Tenant '{tenant_id}' not found")
        tenant.status = "suspended_usage_limit" if suspended else "active"
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        self.db.refresh(tenant)
        return TenantView(tenant.id, tenant.name, tenant.slug, tenant.timezone, tenant.status)
