from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext, require_roles
from app.db.session import get_db
from app.schemas.integrations import (
    VoiceProviderConfigRequest,
    VoiceProviderConfigResponse,
    VoiceAgentConfigRequest,
    VoiceAgentConfigResponse,
    VoiceCallActionRequest,
    VoiceCallActionResponse,
    VoiceCallResponse,
)
from app.services.voice_config_service import VoiceConfigService
from app.services.voice_agent_service import VoiceAgentService
from app.services.voice_call_service import VoiceCallService

router = APIRouter(prefix="/api/v1", tags=["Voice CRM"])


# Voice Configs
@router.post("/integrations/voice/config", response_model=VoiceProviderConfigResponse)
def upsert_voice_config(
    body: VoiceProviderConfigRequest,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin"])),
    db: Session = Depends(get_db),
) -> Any:
    service = VoiceConfigService(db)
    try:
        config = service.upsert_provider_config(context.tenant.id, body)
        return service.get_config_response(context.tenant.id, config.provider)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/integrations/voice/config", response_model=VoiceProviderConfigResponse)
def get_voice_config(
    provider: str = "ultravox",
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst"])),
    db: Session = Depends(get_db),
) -> Any:
    service = VoiceConfigService(db)
    return service.get_config_response(context.tenant.id, provider)


def _test_voice_config_for_tenant(
    tenant_id: str,
    provider: str,
    db: Session,
) -> dict[str, Any]:
    service = VoiceConfigService(db)
    health_status, error_message = service.test_connection(tenant_id, provider)
    return {"status": health_status, "error": error_message}


@router.post("/integrations/voice/test", response_model=dict[str, Any])
def test_voice_config(
    provider: str = "ultravox",
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin"])),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return _test_voice_config_for_tenant(
            tenant_id=context.tenant.id,
            provider=provider,
            db=db,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Voice test failed",
        ) from exc


@router.post("/integrations/voice/config/test", response_model=dict[str, Any])
def test_voice_config_legacy(
    provider: str = "ultravox",
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin"])),
    db: Session = Depends(get_db),
) -> Any:
    return test_voice_config(provider=provider, context=context, db=db)


# Voice Agents
@router.post("/integrations/voice/agents", response_model=VoiceAgentConfigResponse)
def create_voice_agent(
    body: VoiceAgentConfigRequest,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin"])),
    db: Session = Depends(get_db),
) -> Any:
    service = VoiceAgentService(db)
    try:
        agent = service.create_or_update_agent_config(context.tenant.id, body)
        return service.response(agent)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/integrations/voice/agents", response_model=list[VoiceAgentConfigResponse])
def list_voice_agents(
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"])),
    db: Session = Depends(get_db),
) -> Any:
    service = VoiceAgentService(db)
    agents = service.list_agent_configs(context.tenant.id)
    return [service.response(a) for a in agents]


@router.get("/integrations/voice/agents/{agent_id}", response_model=VoiceAgentConfigResponse)
def get_voice_agent(
    agent_id: str,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"])),
    db: Session = Depends(get_db),
) -> Any:
    service = VoiceAgentService(db)
    agent = service.get_agent_config(context.tenant.id, agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice agent not found.")
    return service.response(agent)


@router.put("/integrations/voice/agents/{agent_id}", response_model=VoiceAgentConfigResponse)
def update_voice_agent(
    agent_id: str,
    body: VoiceAgentConfigRequest,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin"])),
    db: Session = Depends(get_db),
) -> Any:
    service = VoiceAgentService(db)
    try:
        agent = service.create_or_update_agent_config(context.tenant.id, body, agent_config_id=agent_id)
        return service.response(agent)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


# CRM Outbound Call Trigger
@router.post("/crm/leads/{lead_id}/actions/call", response_model=VoiceCallActionResponse, status_code=status.HTTP_201_CREATED)
def start_voice_call(
    lead_id: str,
    body: VoiceCallActionRequest | None = None,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst"])),
    db: Session = Depends(get_db),
) -> Any:
    service = VoiceCallService(db)
    req = body or VoiceCallActionRequest()
    try:
        return service.start_lead_call(context.tenant.id, lead_id, req)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/crm/leads/{lead_id}/calls", response_model=list[VoiceCallResponse])
def list_lead_voice_calls(
    lead_id: str,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"])),
    db: Session = Depends(get_db),
) -> Any:
    service = VoiceCallService(db)
    calls = service.list_lead_calls(context.tenant.id, lead_id)
    return [service.response(c) for c in calls]
