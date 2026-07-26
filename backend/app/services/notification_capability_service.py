from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.notifications import TenantCapability


class NotificationCapabilityService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def is_enabled(self, *, tenant_id: str, capability_key: str) -> bool:
        capability = (
            self.db.query(TenantCapability)
            .filter(
                TenantCapability.tenant_id == tenant_id,
                TenantCapability.capability_key == capability_key,
            )
            .first()
        )
        if capability is None:
            return False
        return bool(capability.enabled)
