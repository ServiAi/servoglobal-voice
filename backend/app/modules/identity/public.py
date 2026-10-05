"""Identity / Tenancy -- public API (minimal).

Only tenant feature flags so far; implementation still lives in legacy
app.services.tenant_feature_service. TenantFeatureGrant rows never leave
this module.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services import tenant_feature_service as _features
from app.services.tenant_feature_service import (
    AGENT_BUILDER,
    CUSTOM_HTTP_TOOLS,
    LIVEKIT_SIP_OUTBOUND_V2,
    VOICE_RUNTIME_V2,
)
from app.services.tenant_feature_service import (
    TenantFeatureDisabledError as FeatureDisabledError,
)

__all__ = [
    "AGENT_BUILDER",
    "CUSTOM_HTTP_TOOLS",
    "LIVEKIT_SIP_OUTBOUND_V2",
    "VOICE_RUNTIME_V2",
    "FeatureDisabledError",
    "FeatureFlags",
    "MembershipDirectory",
]


class FeatureFlags:
    def __init__(self, db: Session) -> None:
        self.db = db

    def is_enabled(self, tenant_id: str, feature_key: str) -> bool:
        return _features.TenantFeatureService(self.db).is_enabled(tenant_id, feature_key)

    def require_enabled(self, tenant_id: str, feature_key: str) -> None:
        """Raises FeatureDisabledError."""
        _features.TenantFeatureService(self.db).require_enabled(tenant_id, feature_key)


class MembershipDirectory:
    """Who belongs to a tenant (Identity owns users and memberships)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def is_active_member(self, tenant_id: str, user_id: str) -> bool:
        from sqlalchemy import select

        from app.models.identity import TenantMembership

        return (
            self.db.scalar(
                select(TenantMembership.id).where(
                    TenantMembership.tenant_id == tenant_id,
                    TenantMembership.user_id == user_id,
                    TenantMembership.status == "active",
                )
            )
            is not None
        )
