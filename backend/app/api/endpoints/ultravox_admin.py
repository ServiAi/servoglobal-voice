from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext
from app.api.endpoints.integrations import require_enabled_integration
from app.db.session import get_db
from app.schemas.ultravox_admin import (
    UltravoxAgentDetail, UltravoxAgentPage, UltravoxImportResponse,
    UltravoxVoicePage, UltravoxVoiceSummary,
)
from app.services.ultravox_admin_service import UltravoxAdminService
from app.services.ultravox_provider_client import UltravoxProviderError


router = APIRouter(
    prefix="/api/v1/integrations/voice/providers/ultravox",
    tags=["Ultravox Administration"],
)
READ_ROLES = ["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"]
WRITE_ROLES = ["platform_admin", "tenant_admin"]


def _error(exc: Exception) -> None:
    if isinstance(exc, UltravoxProviderError):
        status = 404 if exc.code == "provider_resource_not_found" else 409
        raise HTTPException(status_code=status, detail=exc.code) from None
    raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("/agents", response_model=UltravoxAgentPage)
def list_agents(
    cursor: str | None = None,
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    search: str | None = Query(None, min_length=1, max_length=120),
    context: AuthContext = Depends(require_enabled_integration("voice", READ_ROLES)),
    db: Session = Depends(get_db),
):
    try:
        return UltravoxAdminService(db).list_agents(
            context.tenant.id, cursor=cursor, page_size=page_size, search=search
        )
    except (ValueError, UltravoxProviderError) as exc:
        _error(exc)


@router.get("/agents/{agent_id}", response_model=UltravoxAgentDetail)
def get_agent(agent_id: str, context: AuthContext = Depends(require_enabled_integration("voice", READ_ROLES)), db: Session = Depends(get_db)):
    try:
        return UltravoxAdminService(db).get_agent(context.tenant.id, agent_id)
    except (ValueError, UltravoxProviderError) as exc:
        _error(exc)


@router.post("/agents/{agent_id}/import", response_model=UltravoxImportResponse)
def import_agent(agent_id: str, context: AuthContext = Depends(require_enabled_integration("voice", WRITE_ROLES)), db: Session = Depends(get_db)):
    try:
        return UltravoxAdminService(db).import_agent(context.tenant.id, agent_id, context.user.id)
    except (ValueError, UltravoxProviderError) as exc:
        _error(exc)


@router.get("/voices", response_model=UltravoxVoicePage)
def list_voices(
    cursor: str | None = None,
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    search: str | None = Query(None, min_length=1, max_length=120),
    primary_language: str | None = Query(None, alias="primaryLanguage", max_length=16),
    provider: list[str] | None = Query(None),
    billing_style: str | None = Query(None, alias="billingStyle"),
    ownership: str | None = None,
    context: AuthContext = Depends(require_enabled_integration("voice", READ_ROLES)),
    db: Session = Depends(get_db),
):
    try:
        return UltravoxAdminService(db).list_voices(
            context.tenant.id, cursor=cursor, pageSize=page_size, search=search,
            primaryLanguage=primary_language, provider=provider,
            billingStyle=billing_style, ownership=ownership,
        )
    except (ValueError, UltravoxProviderError) as exc:
        _error(exc)


@router.get("/voices/{voice_id}", response_model=UltravoxVoiceSummary)
def get_voice(voice_id: str, context: AuthContext = Depends(require_enabled_integration("voice", READ_ROLES)), db: Session = Depends(get_db)):
    try:
        return UltravoxAdminService(db).get_voice(context.tenant.id, voice_id)
    except (ValueError, UltravoxProviderError) as exc:
        _error(exc)


@router.get("/voices/{voice_id}/preview")
def preview_voice(voice_id: str, context: AuthContext = Depends(require_enabled_integration("voice", READ_ROLES)), db: Session = Depends(get_db)):
    try:
        return Response(
            content=UltravoxAdminService(db).preview(context.tenant.id, voice_id),
            media_type="audio/wav",
            headers={"Cache-Control": "private, no-store"},
        )
    except (ValueError, UltravoxProviderError) as exc:
        _error(exc)
