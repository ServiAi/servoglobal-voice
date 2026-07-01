from __future__ import annotations

from datetime import datetime
from typing import Optional

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
