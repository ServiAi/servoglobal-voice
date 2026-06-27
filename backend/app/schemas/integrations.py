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


class EmailActionRequest(BaseModel):
    template_key: str = Field(default="lead_proposal", min_length=1, max_length=80)
    subject: Optional[str] = Field(None, max_length=255)
    message: Optional[str] = None
    asset_ids: list[str] = Field(default_factory=list)
    preview_only: bool = False


class EmailActionResponse(BaseModel):
    status: str
    email_send_id: Optional[str] = None
    provider_email_id: Optional[str] = None
    preview: Optional[dict] = None
