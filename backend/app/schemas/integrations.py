from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ResendIntegrationConfigRequest(BaseModel):
    sender_email: str = Field(..., min_length=3, max_length=255)
    sender_name: Optional[str] = Field(None, max_length=120)
    reply_to: Optional[str] = Field(None, max_length=255)
    default_domain: Optional[str] = Field(None, max_length=255)
    resend_api_key: Optional[str] = Field(None, max_length=500)


class ResendIntegrationConfigResponse(BaseModel):
    provider: str
    status: str
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    reply_to: Optional[str] = None
    default_domain: Optional[str] = None
    has_secret: bool
    last_health_check_at: Optional[datetime] = None
    last_error_message: Optional[str] = None


class IntegrationAvailabilityResponse(BaseModel):
    provider: str
    enabled: bool


class IntegrationAvailabilityUpdateRequest(BaseModel):
    enabled: bool


class ResendTestEmailRequest(BaseModel):
    to_email: str = Field(..., min_length=3, max_length=255)


class ResendTestEmailResponse(BaseModel):
    status: str
    provider_email_id: Optional[str] = None
    error_message: Optional[str] = None


class EmailTemplateItem(BaseModel):
    id: str
    template_key: str
    name: str
    subject: str
    category: str
    status: str
    is_marketing: bool


class EmailTemplateUpsertRequest(BaseModel):
    template_key: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=120)
    subject: str = Field(..., min_length=1, max_length=255)
    html_body: str = Field(..., min_length=1)
    text_body: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1, max_length=40)
    status: str = "active"


class EmailAssetItem(BaseModel):
    id: str
    original_filename: str
    mime_type: str
    file_size_bytes: int
    status: str


class EmailActionRequest(BaseModel):
    template_key: str = Field(default="lead_proposal", min_length=1, max_length=80)
    subject: Optional[str] = Field(None, max_length=255)
    message: Optional[str] = None
    content_format: str = "mdx"
    content: Optional[str] = None
    asset_ids: list[str] = Field(default_factory=list)
    form_token_ids: list[str] = Field(default_factory=list)
    preview_only: bool = False


class EmailActionResponse(BaseModel):
    status: str
    email_send_id: Optional[str] = None
    provider_email_id: Optional[str] = None
    preview: Optional[dict] = None


class BookingConfigRequest(BaseModel):
    cal_api_key: Optional[str] = Field(None, max_length=500)
    status: str = "active"
    calendar_mode: str = "cal_managed"
    cal_api_version: str = "2024-08-13"
    organization_slug: Optional[str] = Field(None, max_length=120)
    default_event_type_id: Optional[int] = None
    default_event_type_slug: Optional[str] = Field(None, max_length=160)
    default_username: Optional[str] = Field(None, max_length=160)
    default_team_slug: Optional[str] = Field(None, max_length=160)
    default_timezone: str = "America/Bogota"
    default_language: str = "es"
    default_location_type: Optional[str] = Field(None, max_length=80)
    default_length_minutes: int = Field(30, ge=5, le=480)


class BookingConfigResponse(BaseModel):
    provider: str = "calcom"
    status: str
    calendar_mode: str
    has_secret: bool
    default_event_type_id: Optional[int] = None
    default_event_type_slug: Optional[str] = None
    default_username: Optional[str] = None
    default_team_slug: Optional[str] = None
    organization_slug: Optional[str] = None
    default_timezone: str
    default_language: str
    default_location_type: Optional[str] = None
    default_length_minutes: int
    last_health_check_at: Optional[datetime] = None
    last_error_message: Optional[str] = None


class CalComTestResponse(BaseModel):
    status: str
    error_message: Optional[str] = None


class GoogleCalendarConnectUrlResponse(BaseModel):
    url: str


class GoogleCalendarConnectionResponse(BaseModel):
    id: str
    status: str
    google_account_email: Optional[str] = None
    calendar_id: str
    calendar_summary: Optional[str] = None
    scopes: list[str] = Field(default_factory=list)
    last_sync_at: Optional[datetime] = None
    last_error_message: Optional[str] = None
    has_tokens: bool


class WhatsAppConfigRequest(BaseModel):
    phone_number_id: str = Field(..., min_length=1, max_length=120)
    business_account_id: Optional[str] = Field(None, max_length=120)
    display_phone_number: Optional[str] = Field(None, max_length=80)
    default_language: str = Field(default="es", max_length=16)
    status: str = "active"
    access_token: Optional[str] = Field(None, max_length=2000)
    webhook_verify_token: Optional[str] = Field(None, max_length=500)


class WhatsAppConfigResponse(BaseModel):
    provider: str = "whatsapp_cloud"
    status: str
    phone_number_id: Optional[str] = None
    business_account_id: Optional[str] = None
    display_phone_number: Optional[str] = None
    default_language: str = "es"
    has_secret: bool
    has_webhook_secret: bool = False
    voice_calling_enabled: bool = False
    last_health_check_at: Optional[datetime] = None
    last_error_message: Optional[str] = None


class WhatsAppTestRequest(BaseModel):
    pass


class WhatsAppTestResponse(BaseModel):
    status: str
    message: Optional[str] = None
    sends_message: bool = False
    error_message: Optional[str] = None


class WhatsAppTemplateSyncResponse(BaseModel):
    status: str
    fetched_count: int = 0
    approved_count: int = 0
    synced_count: int = 0
    ignored_count: int = 0
    error_message: Optional[str] = None


class WhatsAppTestMessageRequest(BaseModel):
    to_phone: str = Field(..., min_length=8, max_length=32)
    template_key: Optional[str] = Field(None, max_length=80)
    provider_template_name: Optional[str] = Field(None, max_length=120)
    language: Optional[str] = Field(None, max_length=16)
    variables: dict[str, str] = Field(default_factory=dict)


class WhatsAppTestMessageResponse(BaseModel):
    status: str
    whatsapp_message_id: Optional[str] = None
    provider_message_id: Optional[str] = None
    template_key: Optional[str] = None
    to_phone_masked: Optional[str] = None
    message: Optional[str] = None
    error_message: Optional[str] = None


class WhatsAppTemplateResponse(BaseModel):
    id: str
    template_key: str
    provider_template_name: str
    name: str
    category: str
    language: str
    body: str
    variables: dict[str, Any] = Field(default_factory=dict)
    status: str


class WhatsAppTemplateButtonItem(BaseModel):
    type: str = Field(..., pattern=r"^(QUICK_REPLY|URL|PHONE_NUMBER|VOICE_CALL|FLOW)$")
    text: str = Field(..., min_length=1, max_length=25)
    url: Optional[str] = Field(None, max_length=2000)
    phone_number: Optional[str] = Field(None, max_length=32)
    flow_id: Optional[str] = Field(None, max_length=120)
    flow_action: Optional[str] = Field(None, max_length=32)
    navigate_screen: Optional[str] = Field(None, max_length=120)


class WhatsAppTemplateCreateRequest(BaseModel):
    template_key: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=120)
    category: str = Field(..., min_length=1, max_length=40)
    language: str = Field(default="es", max_length=16)
    header_text: Optional[str] = Field(None, max_length=60)
    body: str = Field(..., min_length=1, max_length=1024)
    footer_text: Optional[str] = Field(None, max_length=60)
    buttons: list[WhatsAppTemplateButtonItem] = Field(default_factory=list)


class WhatsAppTemplateUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    header_text: Optional[str] = Field(None, max_length=60)
    body: Optional[str] = Field(None, min_length=1, max_length=1024)
    footer_text: Optional[str] = Field(None, max_length=60)
    buttons: Optional[list[WhatsAppTemplateButtonItem]] = None


class WhatsAppTemplateDetailResponse(WhatsAppTemplateResponse):
    meta_status: Optional[str] = None
    provider_template_id: Optional[str] = None
    source: str = "tenant_authored"
    parameter_format: str = "POSITIONAL"
    header_text: Optional[str] = None
    footer_text: Optional[str] = None
    buttons: list[WhatsAppTemplateButtonItem] = Field(default_factory=list)
    rejection_reason: Optional[str] = None
    last_synced_at: Optional[datetime] = None


class WhatsAppTemplatePreviewResponse(BaseModel):
    header_text: Optional[str] = None
    body: str
    footer_text: Optional[str] = None
    buttons: list[WhatsAppTemplateButtonItem] = Field(default_factory=list)
    variables: dict[str, str] = Field(default_factory=dict)


class WhatsAppTemplateSubmitResponse(BaseModel):
    status: str
    meta_status: Optional[str] = None
    provider_template_id: Optional[str] = None
    error_message: Optional[str] = None


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


class VoiceCallActionRequest(BaseModel):
    agent_config_id: Optional[str] = None
    to_phone: Optional[str] = Field(None, max_length=80)
    context: dict[str, Any] = Field(default_factory=dict)


class VoiceCallActionResponse(BaseModel):
    status: str
    voice_call_id: str
    provider_call_id: Optional[str] = None
    provider_session_id: Optional[str] = None
    provider_call_id: Optional[str] = None
    provider_session_id: Optional[str] = None
    summary: Optional[str] = None


class VoiceCallResponse(BaseModel):
    id: str
    provider: str
    provider_call_id: Optional[str] = None
    provider_session_id: Optional[str] = None
    provider_agent_id: Optional[str] = None
    direction: str
    status: str
    started_at: Optional[datetime] = None
    answered_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    summary: Optional[str] = None
    created_at: datetime
