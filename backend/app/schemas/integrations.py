from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class VoiceSipRouteRequest(BaseModel):
    status: str = Field(default="inactive", pattern=r"^(active|inactive)$")
    pbx_host: str = Field(min_length=1, max_length=255)
    pbx_port: int = Field(default=5060, ge=1, le=65535)
    sip_password: Optional[str] = Field(None, min_length=8, max_length=1000)
    caller_id: str = Field(min_length=7, max_length=32)
    default_country: str = Field(default="CO", pattern=r"^(AR|CL|CO|EC|MX|PA|PE|US)$")
    allowed_countries: list[str] = Field(default_factory=lambda: ["CO"])
    max_concurrent_calls: int = Field(default=1, ge=1, le=100)


class VoiceSipRouteResponse(BaseModel):
    id: str
    status: str
    pbx_host: str
    pbx_port: int
    sip_username: str
    caller_id: str
    default_country: str
    allowed_countries: list[str]
    max_concurrent_calls: int
    has_sip_password: bool
    provision_status: str
    desired_revision: int
    applied_revision: int
    provision_error_code: Optional[str] = None
    provisioned_at: Optional[datetime] = None
    last_provision_attempt_at: Optional[datetime] = None
    livekit_outbound_trunk_id: Optional[str] = None
    livekit_provision_status: str = "disabled"
    livekit_provision_error_code: Optional[str] = None
    livekit_provisioned_at: Optional[datetime] = None


class VoiceProviderConfigRequest(BaseModel):
    provider: str = Field(default="ultravox", max_length=40)
    status: str = Field(default="active", max_length=32)
    display_name: Optional[str] = Field(None, max_length=120)
    base_url: Optional[str] = Field(None, max_length=255)
    default_voice_agent_id: Optional[str] = Field(None, max_length=120)
    default_from_number: Optional[str] = Field(None, max_length=80)
    default_language: str = Field(default="es", max_length=16)
    default_timezone: str = Field(default="America/Bogota", max_length=80)
    api_key: Optional[str] = Field(None, max_length=1000)
    webhook_secret: Optional[str] = Field(None, max_length=1000)
    sip_route: Optional[VoiceSipRouteRequest] = None


class VoiceProviderConfigResponse(BaseModel):
    id: str
    provider: str = "ultravox"
    status: str
    display_name: Optional[str] = None
    base_url: Optional[str] = None
    default_voice_agent_id: Optional[str] = None
    default_from_number: Optional[str] = None
    default_language: str = "es"
    default_timezone: str = "America/Bogota"
    has_secret: bool
    has_webhook_secret: bool = False
    last_health_check_at: Optional[datetime] = None
    last_error_message: Optional[str] = None
    sip_route: Optional[VoiceSipRouteResponse] = None


# Triggers de handoff a humano soportados hoy. "customer_request" lo dispara
# una tool explicita que el agente invoca; "lead_score" se revisa cuando el
# agente invoca cualquier tool de voz (no hay analisis en vivo de la llamada
# fuera de esos puntos). Sentimiento/tool-failure/"no puedo resolver" quedan
# para una fase posterior.
HANDOFF_TRIGGER_CUSTOMER_REQUEST = "customer_request"
HANDOFF_TRIGGER_LEAD_SCORE = "lead_score"
VALID_HANDOFF_TRIGGERS = {HANDOFF_TRIGGER_CUSTOMER_REQUEST, HANDOFF_TRIGGER_LEAD_SCORE}


class VoiceAgentConfigRequest(BaseModel):
    provider_config_id: Optional[str] = None
    provider: str = Field(default="ultravox", max_length=40)
    provider_agent_id: str = Field(..., min_length=1, max_length=120)
    display_name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = None
    purpose: str = Field(default="Atención al Cliente", max_length=80)
    default_language: str = Field(default="es", max_length=16)
    default_timezone: str = Field(default="America/Bogota", max_length=80)
    default_voice: Optional[str] = Field(None, max_length=80)
    default_system_prompt: Optional[str] = None
    default_tools_json: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="active", max_length=32)
    handoff_enabled: bool = False
    handoff_chatwoot_inbox_id: Optional[int] = Field(None, gt=0)
    handoff_chatwoot_team_id: Optional[int] = Field(None, gt=0)
    handoff_triggers: list[str] = Field(default_factory=list)
    handoff_lead_score_threshold: int = Field(default=80, ge=0, le=100)

    @field_validator("handoff_triggers")
    @classmethod
    def _validate_handoff_triggers(cls, value: list[str]) -> list[str]:
        invalid = set(value) - VALID_HANDOFF_TRIGGERS
        if invalid:
            raise ValueError(f"Unsupported handoff triggers: {sorted(invalid)}")
        return value


class VoiceAgentConfigResponse(BaseModel):
    id: str
    provider: str = "ultravox"
    provider_agent_id: str
    display_name: str
    description: Optional[str] = None
    purpose: str
    default_language: str
    default_timezone: str
    default_voice: Optional[str] = None
    status: str
    handoff_enabled: bool = False
    handoff_chatwoot_inbox_id: Optional[int] = None
    handoff_chatwoot_team_id: Optional[int] = None
    handoff_triggers: list[str] = Field(default_factory=list)
    handoff_lead_score_threshold: int = 80


class VoiceCallActionRequest(BaseModel):
    agent_config_id: Optional[str] = None
    agent_id: Optional[str] = Field(None, min_length=1, max_length=36)
    idempotency_key: Optional[str] = Field(None, min_length=1, max_length=160)
    to_phone: Optional[str] = Field(None, max_length=80)
    context: dict[str, Any] = Field(default_factory=dict)


class VoiceCallActionResponse(BaseModel):
    status: str
    voice_call_id: str
    provider_call_id: Optional[str] = None
    provider_session_id: Optional[str] = None
    voice_session_id: Optional[str] = None
    sip_call_id: Optional[str] = None
    summary: Optional[str] = None


class VoiceCallResponse(BaseModel):
    id: str
    provider: str
    provider_call_id: Optional[str] = None
    provider_session_id: Optional[str] = None
    provider_agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    direction: str
    status: str
    started_at: Optional[datetime] = None
    answered_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    summary: Optional[str] = None
    created_at: datetime
