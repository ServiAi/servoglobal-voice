from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext
from app.api.deps import require_enabled_integration
from app.db.session import get_db
from app.schemas.integrations import (
    VoiceAgentConfigRequest,
    VoiceAgentConfigResponse,
    VoiceProviderConfigRequest,
    VoiceProviderConfigResponse,
)
from app.services.voice_agent_service import VoiceAgentService
from app.services.voice_config_service import VoiceConfigService

# Voice provider/agent config stays with its legacy owner; only the URL prefix is shared
# with the Integrations catalog.
router = APIRouter(prefix="/api/v1/integrations", tags=["Integrations"])

_READ_ROLES = ["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"]
_WRITE_ROLES = ["platform_admin", "tenant_admin"]


@router.get("/voice/config", response_model=VoiceProviderConfigResponse)
def get_voice_config(
    context: AuthContext = Depends(require_enabled_integration("voice", _READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    return VoiceConfigService(db).get_config_response(context.tenant.id)


@router.post("/voice/config", response_model=VoiceProviderConfigResponse)
def configure_voice(
    body: VoiceProviderConfigRequest,
    context: AuthContext = Depends(require_enabled_integration("voice", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        config = VoiceConfigService(db).upsert_provider_config(context.tenant.id, body)
        return VoiceConfigService(db).get_config_response(context.tenant.id, config.provider)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/voice/test")
def test_voice(
    provider: str = "ultravox",
    context: AuthContext = Depends(require_enabled_integration("voice", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        result, error = VoiceConfigService(db).test_connection(context.tenant.id, provider)
        if result != "active":
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error or "Voice test failed.")
        return {"status": result}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


# --- Voice Agent Config ---

@router.get("/voice/agents", response_model=list[VoiceAgentConfigResponse])
def list_voice_agents(
    context: AuthContext = Depends(require_enabled_integration("voice", _READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = VoiceAgentService(db)
    agents = service.list_agent_configs(context.tenant.id)
    return [service.response(agent) for agent in agents]


@router.post("/voice/agents", response_model=VoiceAgentConfigResponse)
def create_voice_agent(
    body: VoiceAgentConfigRequest,
    context: AuthContext = Depends(require_enabled_integration("voice", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        service = VoiceAgentService(db)
        agent = service.create_or_update_agent_config(context.tenant.id, body)
        return service.response(agent)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.put("/voice/agents/{agent_config_id}", response_model=VoiceAgentConfigResponse)
def update_voice_agent(
    agent_config_id: str,
    body: VoiceAgentConfigRequest,
    context: AuthContext = Depends(require_enabled_integration("voice", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        service = VoiceAgentService(db)
        agent = service.create_or_update_agent_config(context.tenant.id, body, agent_config_id)
        return service.response(agent)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
