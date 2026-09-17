from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext
from app.api.endpoints.integrations import require_enabled_integration
from app.db.session import get_db
from app.schemas.agents import AgentVoiceConfig
from app.schemas.ultravox_admin import (
    UltravoxAgentDetail, UltravoxAgentPage, UltravoxImportResponse,
    UltravoxVoicePage, UltravoxVoiceSummary,
)
from app.services.ultravox_provider_client import PREVIEW_REJECTION_REASONS, UltravoxProviderError
from app.services.voice_provider_admin import (
    VoiceProviderNotAvailableError, get_provider_admin_service,
)


router = APIRouter(
    prefix="/api/v1/integrations/voice/providers/{provider}",
    tags=["Voice Provider Administration"],
)
READ_ROLES = ["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"]
WRITE_ROLES = ["platform_admin", "tenant_admin"]


def _error(exc: Exception) -> None:
    if isinstance(exc, VoiceProviderNotAvailableError):
        raise HTTPException(status_code=404, detail="provider_not_available") from None
    if isinstance(exc, UltravoxProviderError):
        if exc.code == "voice_preview_rejected":
            reason = exc.reason if exc.reason in PREVIEW_REJECTION_REASONS else "other"
            raise HTTPException(
                status_code=409,
                detail={"code": "voice_preview_rejected", "reason": reason, "provider": "ultravox"},
            ) from None
        status = 404 if exc.code == "provider_resource_not_found" else 409
        raise HTTPException(status_code=status, detail=exc.code) from None
    raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("/agents", response_model=UltravoxAgentPage)
def list_agents(
    provider: str,
    cursor: str | None = None,
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    search: str | None = Query(None, min_length=1, max_length=120),
    context: AuthContext = Depends(require_enabled_integration("voice", READ_ROLES)),
    db: Session = Depends(get_db),
):
    try:
        service = get_provider_admin_service(db, provider)
        return service.list_agents(context.tenant.id, cursor=cursor, page_size=page_size, search=search)
    except (ValueError, UltravoxProviderError) as exc:
        _error(exc)


@router.get("/agents/{agent_id}", response_model=UltravoxAgentDetail)
def get_agent(provider: str, agent_id: str, context: AuthContext = Depends(require_enabled_integration("voice", READ_ROLES)), db: Session = Depends(get_db)):
    try:
        service = get_provider_admin_service(db, provider)
        return service.get_agent(context.tenant.id, agent_id)
    except (ValueError, UltravoxProviderError) as exc:
        _error(exc)


@router.post("/agents/{agent_id}/import", response_model=UltravoxImportResponse)
def import_agent(provider: str, agent_id: str, context: AuthContext = Depends(require_enabled_integration("voice", WRITE_ROLES)), db: Session = Depends(get_db)):
    try:
        service = get_provider_admin_service(db, provider)
        return service.import_agent(context.tenant.id, agent_id, context.user.id)
    except (ValueError, UltravoxProviderError) as exc:
        _error(exc)


@router.get("/voices", response_model=UltravoxVoicePage)
def list_voices(
    provider: str,
    cursor: str | None = None,
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    search: str | None = Query(None, min_length=1, max_length=120),
    primary_language: str | None = Query(None, alias="primaryLanguage", max_length=16),
    provider_filter: list[str] | None = Query(None, alias="provider"),
    billing_style: str | None = Query(None, alias="billingStyle"),
    ownership: str | None = None,
    context: AuthContext = Depends(require_enabled_integration("voice", READ_ROLES)),
    db: Session = Depends(get_db),
):
    try:
        service = get_provider_admin_service(db, provider)
        return service.list_voices(
            context.tenant.id, cursor=cursor, pageSize=page_size, search=search,
            primaryLanguage=primary_language, provider=provider_filter,
            billingStyle=billing_style, ownership=ownership,
        )
    except (ValueError, UltravoxProviderError) as exc:
        _error(exc)


@router.get("/voices/{voice_id}", response_model=UltravoxVoiceSummary)
def get_voice(provider: str, voice_id: str, context: AuthContext = Depends(require_enabled_integration("voice", READ_ROLES)), db: Session = Depends(get_db)):
    try:
        service = get_provider_admin_service(db, provider)
        return service.get_voice(context.tenant.id, voice_id)
    except (ValueError, UltravoxProviderError) as exc:
        _error(exc)


@router.get("/voices/{voice_id}/preview")
def preview_voice(provider: str, voice_id: str, context: AuthContext = Depends(require_enabled_integration("voice", READ_ROLES)), db: Session = Depends(get_db)):
    try:
        service = get_provider_admin_service(db, provider)
        preview = service.preview(context.tenant.id, voice_id)
        return Response(
            content=preview.content,
            media_type=preview.media_type,
            headers={"Cache-Control": "private, no-store"},
        )
    except (ValueError, UltravoxProviderError) as exc:
        _error(exc)


@router.post("/external-voice/preview")
def preview_external_voice(
    provider: str,
    body: AgentVoiceConfig,
    # "Probar voz" generates real, potentially billable audio, so it uses
    # WRITE_ROLES (platform_admin, tenant_admin) rather than READ_ROLES --
    # a tenant_viewer must not be able to trigger provider generation.
    context: AuthContext = Depends(require_enabled_integration("voice", WRITE_ROLES)),
    db: Session = Depends(get_db),
):
    try:
        service = get_provider_admin_service(db, provider)
        preview = service.preview_external_voice(context.tenant.id, body)
    except (ValueError, UltravoxProviderError) as exc:
        _error(exc)
    else:
        return Response(
            content=preview.content,
            media_type=preview.media_type,
            headers={"Cache-Control": "private, no-store"},
        )
