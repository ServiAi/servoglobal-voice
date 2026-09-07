from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.endpoints.admin.tenants import get_current_internal_user
from app.db.session import get_db
from app.models.identity import User
from app.models.tenant_features import TenantFeatureGrant
from app.schemas.tenant_features import (
    AgentBuilderFeatureUpdate,
    TenantFeatureResponse,
    VoiceExperiencesFeatureUpdate,
    WhatsAppBusinessCallingFeatureUpdate,
)
from app.services.tenant_feature_service import (
    AGENT_BUILDER,
    TenantFeatureService,
    TenantFeatureTenantNotFoundError,
    VOICE_EXPERIENCES,
    WHATSAPP_BUSINESS_CALLING,
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


@router.put(
    "/{tenant_id}/features/agent-builder-v2",
    response_model=TenantFeatureResponse,
)
def set_agent_builder_feature(
    tenant_id: str,
    body: AgentBuilderFeatureUpdate,
    user: User = Depends(get_current_internal_user),
    db: Session = Depends(get_db),
) -> TenantFeatureResponse:
    try:
        grant = TenantFeatureService(db).set_feature(
            tenant_id=tenant_id,
            feature_key=AGENT_BUILDER,
            enabled=body.enabled,
            limits={},
            enabled_by_user_id=user.id,
        )
    except TenantFeatureTenantNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _response(grant)


@router.put(
    "/{tenant_id}/features/whatsapp-business-calling",
    response_model=TenantFeatureResponse,
)
def set_whatsapp_business_calling_feature(
    tenant_id: str,
    body: WhatsAppBusinessCallingFeatureUpdate,
    user: User = Depends(get_current_internal_user),
    db: Session = Depends(get_db),
) -> TenantFeatureResponse:
    try:
        grant = TenantFeatureService(db).set_feature(
            tenant_id=tenant_id,
            feature_key=WHATSAPP_BUSINESS_CALLING,
            enabled=body.enabled,
            limits={},
            enabled_by_user_id=user.id,
        )
    except TenantFeatureTenantNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _response(grant)
