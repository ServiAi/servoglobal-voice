"""Request/response schemas of the Integrations / Messaging API (catalog, Resend, WhatsApp, Chatwoot)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

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


class ChatwootConfigRequest(BaseModel):
    base_url: str = Field(default="https://crm.serviglobal-ia.com", max_length=255)
    account_id: int = Field(..., gt=0)
    default_inbox_id: Optional[int] = Field(None, gt=0)
    status: str = "active"
    api_token: Optional[str] = Field(None, max_length=2000)


class ChatwootProvisionRequest(BaseModel):
    account_name: Optional[str] = Field(None, max_length=160)


class ChatwootConfigResponse(BaseModel):
    provider: str = "chatwoot"
    mode: str = "external"
    status: str
    base_url: Optional[str] = None
    account_id: Optional[int] = None
    account_name: Optional[str] = None
    default_inbox_id: Optional[int] = None
    default_inbox_name: Optional[str] = None
    has_secret: bool
    webhook_url: Optional[str] = None
    last_health_check_at: Optional[datetime] = None
    last_error_message: Optional[str] = None


class ChatwootTestResponse(BaseModel):
    status: str
    error_message: Optional[str] = None


class IntegrationAvailabilityResponse(BaseModel):
    provider: str
    enabled: bool


class IntegrationCatalogStatusResponse(BaseModel):
    provider: str
    status: Literal["active", "configured", "not_configured", "error"]


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


class ChatwootInboxSummary(BaseModel):
    id: int
    name: str
    channel_type: Optional[str] = None


class ChatwootInboxCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)


class ChatwootInboxUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)


class ChatwootTeamSummary(BaseModel):
    id: int
    name: str


class ChatwootTeamCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    description: Optional[str] = Field(None, max_length=500)


class ChatwootTeamUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=160)
    description: Optional[str] = Field(None, max_length=500)


class ChatwootAgentSummary(BaseModel):
    id: int
    name: str
    email: str
    role: str
    confirmed: bool = True


class ChatwootAgentInviteRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    email: str = Field(..., min_length=3, max_length=255)
    role: Literal["agent", "administrator"] = "agent"


class ChatwootAgentUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=160)
    role: Optional[Literal["agent", "administrator"]] = None
