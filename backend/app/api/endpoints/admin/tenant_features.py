from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.endpoints.admin.tenants import get_current_internal_user
from app.db.session import get_db
from app.models.identity import User
from app.models.tenant_features import TenantFeatureGrant
from app.schemas.tenant_features import (
    TenantFeatureResponse,
    VoiceExperiencesFeatureUpdate,
)
from app.services.tenant_feature_service import (
    TenantFeatureService,
    TenantFeatureTenantNotFoundError,
    VOICE_EXPERIENCES,
)


router = APIRouter(prefix="/api/v1/admin/tenants", tags=["admin-tenant-features"])


def _response(grant: TenantFeatureGrant) -> TenantFeatureResponse:
    return TenantFeatureResponse(
        feature_key=grant.feature_key,
        enabled=grant.enabled,
        limits=grant.limits_json,
        created_at=grant.created_at,
        updated_at=grant.updated_at,
    )


@router.get("/{tenant_id}/features", response_model=list[TenantFeatureResponse])
def list_tenant_features(
    tenant_id: str,
    _user: User = Depends(get_current_internal_user),
    db: Session = Depends(get_db),
) -> list[TenantFeatureResponse]:
    try:
        grants = TenantFeatureService(db).list_features(tenant_id)
    except TenantFeatureTenantNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [_response(grant) for grant in grants]


@router.put(
    "/{tenant_id}/features/voice-experiences",
    response_model=TenantFeatureResponse,
)
def set_voice_experiences_feature(
    tenant_id: str,
    body: VoiceExperiencesFeatureUpdate,
    user: User = Depends(get_current_internal_user),
    db: Session = Depends(get_db),
) -> TenantFeatureResponse:
    try:
        grant = TenantFeatureService(db).set_feature(
            tenant_id=tenant_id,
            feature_key=VOICE_EXPERIENCES,
            enabled=body.enabled,
            limits=body.limits.model_dump(),
            enabled_by_user_id=user.id,
        )
    except TenantFeatureTenantNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _response(grant)
