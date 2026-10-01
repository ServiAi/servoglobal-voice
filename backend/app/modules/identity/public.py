"""Identity / Tenancy -- public API (minimal).

Only tenant feature flags so far; implementation still lives in legacy
app.services.tenant_feature_service. TenantFeatureGrant rows never leave
this module.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services import tenant_feature_service as _features
from app.services.tenant_feature_service import (
    CUSTOM_HTTP_TOOLS,
)
from app.services.tenant_feature_service import (
    TenantFeatureDisabledError as FeatureDisabledError,
)

__all__ = ["CUSTOM_HTTP_TOOLS", "FeatureDisabledError", "FeatureFlags"]


class FeatureFlags:
    def __init__(self, db: Session) -> None:
        self.db = db

    def is_enabled(self, tenant_id: str, feature_key: str) -> bool:
        return _features.TenantFeatureService(self.db).is_enabled(tenant_id, feature_key)

    def require_enabled(self, tenant_id: str, feature_key: str) -> None:
        """Raises FeatureDisabledError."""
        _features.TenantFeatureService(self.db).require_enabled(tenant_id, feature_key)
