from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.identity.domain.errors import (
    FeatureDisabledError,
    TenantFeatureTenantNotFoundError,
    UnknownTenantFeatureError,
)
from app.modules.identity.domain.features import (
    AGENT_BUILDER,
    CUSTOM_HTTP_TOOLS,
    LIVEKIT_SIP_OUTBOUND_V2,
    SUPPORTED_FEATURES,
    VOICE_EXPERIENCES,
    VOICE_RUNTIME_V2,
    WHATSAPP_BUSINESS_CALLING,
)
from app.modules.identity.infrastructure.models import Tenant, TenantFeatureGrant

_UNIQUE_CONSTRAINT_NAME = "uq_tenant_feature_grants_tenant_feature_key"
TenantFeatureDisabledError = FeatureDisabledError


def _is_feature_grant_unique_violation(error: IntegrityError) -> bool:
    original = error.orig
    diagnostic = getattr(original, "diag", None)
    if getattr(diagnostic, "constraint_name", None) == _UNIQUE_CONSTRAINT_NAME:
        return True
    return "tenant_feature_grants.tenant_id, tenant_feature_grants.feature_key" in str(original)


def _validated_limits(feature_key: str, limits: Mapping[str, object]) -> dict[str, object]:
    result = dict(limits)
    if feature_key == VOICE_EXPERIENCES:
        expected = {"max_experiences", "max_context_fields"}
        if result.keys() != expected or any(
            isinstance(result[key], bool)
            or not isinstance(result[key], int)
            or result[key] < 1
            for key in expected
        ):
            raise ValueError("Invalid limits for voice_experiences")
    elif result:
        raise ValueError(f"Feature '{feature_key}' does not accept limits")
    return result


class TenantFeatureService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_features(self, tenant_id: str) -> list[TenantFeatureGrant]:
        self._require_tenant(tenant_id)
        return list(self.db.scalars(
            select(TenantFeatureGrant)
            .where(TenantFeatureGrant.tenant_id == tenant_id)
            .order_by(TenantFeatureGrant.feature_key)
        ).all())

    def get_feature(self, tenant_id: str, feature_key: str) -> TenantFeatureGrant | None:
        self._validate_feature_key(feature_key)
        self._require_tenant(tenant_id)
        return self.db.scalar(select(TenantFeatureGrant).where(
            TenantFeatureGrant.tenant_id == tenant_id,
            TenantFeatureGrant.feature_key == feature_key,
        ))

    def set_feature(
        self,
        tenant_id: str,
        feature_key: str,
        enabled: bool,
        limits: Mapping[str, object],
        enabled_by_user_id: str | None,
    ) -> TenantFeatureGrant:
        self._validate_feature_key(feature_key)
        self._require_tenant(tenant_id)
        validated_limits = _validated_limits(feature_key, limits)
        grant = self.db.scalar(select(TenantFeatureGrant).where(
            TenantFeatureGrant.tenant_id == tenant_id,
            TenantFeatureGrant.feature_key == feature_key,
        ))
        is_new = grant is None
        if grant is None:
            grant = TenantFeatureGrant(tenant_id=tenant_id, feature_key=feature_key)
            self.db.add(grant)
        grant.enabled = enabled
        grant.limits_json = validated_limits
        grant.enabled_by_user_id = enabled_by_user_id
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            if not is_new or not _is_feature_grant_unique_violation(exc):
                raise
            grant = self.db.scalar(select(TenantFeatureGrant).where(
                TenantFeatureGrant.tenant_id == tenant_id,
                TenantFeatureGrant.feature_key == feature_key,
            ))
            if grant is None:
                raise
            grant.enabled = enabled
            grant.limits_json = validated_limits
            grant.enabled_by_user_id = enabled_by_user_id
            self.db.commit()
        self.db.refresh(grant)
        return grant

    def is_enabled(self, tenant_id: str, feature_key: str) -> bool:
        grant = self.get_feature(tenant_id, feature_key)
        return bool(grant and grant.enabled)

    def require_enabled(self, tenant_id: str, feature_key: str) -> TenantFeatureGrant:
        grant = self.get_feature(tenant_id, feature_key)
        if grant is None or not grant.enabled:
            raise FeatureDisabledError(
                f"Feature '{feature_key}' is not enabled for tenant '{tenant_id}'"
            )
        return grant

    def _require_tenant(self, tenant_id: str) -> None:
        if self.db.get(Tenant, tenant_id) is None:
            raise TenantFeatureTenantNotFoundError(f"Tenant '{tenant_id}' not found")

    @staticmethod
    def _validate_feature_key(feature_key: str) -> None:
        if feature_key not in SUPPORTED_FEATURES:
            raise UnknownTenantFeatureError(f"Unknown tenant feature: '{feature_key}'")


__all__ = [
    "AGENT_BUILDER", "CUSTOM_HTTP_TOOLS", "LIVEKIT_SIP_OUTBOUND_V2",
    "VOICE_EXPERIENCES", "VOICE_RUNTIME_V2", "WHATSAPP_BUSINESS_CALLING",
    "FeatureDisabledError", "TenantFeatureService", "TenantFeatureTenantNotFoundError",
    "UnknownTenantFeatureError",
]

