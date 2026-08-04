from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.identity import Tenant
from app.models.tenant_features import TenantFeatureGrant
from app.schemas.tenant_features import VoiceExperienceLimits


VOICE_EXPERIENCES = "voice_experiences"
SUPPORTED_FEATURES = frozenset({VOICE_EXPERIENCES})


class UnknownTenantFeatureError(ValueError):
    pass


class TenantFeatureTenantNotFoundError(ValueError):
    pass


class TenantFeatureDisabledError(PermissionError):
    pass


class TenantFeatureService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_features(self, tenant_id: str) -> list[TenantFeatureGrant]:
        self._require_tenant(tenant_id)
        return list(
            self.db.scalars(
                select(TenantFeatureGrant)
                .where(TenantFeatureGrant.tenant_id == tenant_id)
                .order_by(TenantFeatureGrant.feature_key)
            ).all()
        )

    def get_feature(
        self, tenant_id: str, feature_key: str
    ) -> TenantFeatureGrant | None:
        self._validate_feature_key(feature_key)
        self._require_tenant(tenant_id)
        return self.db.scalar(
            select(TenantFeatureGrant).where(
                TenantFeatureGrant.tenant_id == tenant_id,
                TenantFeatureGrant.feature_key == feature_key,
            )
        )

    def set_feature(
        self,
        tenant_id: str,
        feature_key: str,
        enabled: bool,
        limits: dict,
        enabled_by_user_id: str | None,
    ) -> TenantFeatureGrant:
        self._validate_feature_key(feature_key)
        self._require_tenant(tenant_id)
        validated_limits = VoiceExperienceLimits.model_validate(limits).model_dump()
        grant = self.db.scalar(
            select(TenantFeatureGrant).where(
                TenantFeatureGrant.tenant_id == tenant_id,
                TenantFeatureGrant.feature_key == feature_key,
            )
        )
        if grant is None:
            grant = TenantFeatureGrant(
                tenant_id=tenant_id,
                feature_key=feature_key,
            )
            self.db.add(grant)
        grant.enabled = enabled
        grant.limits_json = validated_limits
        grant.enabled_by_user_id = enabled_by_user_id
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            grant = self.db.scalar(
                select(TenantFeatureGrant).where(
                    TenantFeatureGrant.tenant_id == tenant_id,
                    TenantFeatureGrant.feature_key == feature_key,
                )
            )
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

    def require_enabled(
        self, tenant_id: str, feature_key: str
    ) -> TenantFeatureGrant:
        grant = self.get_feature(tenant_id, feature_key)
        if grant is None or not grant.enabled:
            raise TenantFeatureDisabledError(
                f"Feature '{feature_key}' is not enabled for tenant '{tenant_id}'"
            )
        return grant

    def _require_tenant(self, tenant_id: str) -> None:
        if self.db.get(Tenant, tenant_id) is None:
            raise TenantFeatureTenantNotFoundError(
                f"Tenant '{tenant_id}' not found"
            )

    @staticmethod
    def _validate_feature_key(feature_key: str) -> None:
        if feature_key not in SUPPORTED_FEATURES:
            raise UnknownTenantFeatureError(
                f"Unknown tenant feature: '{feature_key}'"
            )
