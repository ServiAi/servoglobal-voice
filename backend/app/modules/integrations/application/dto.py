"""Commands and results of the application layer (frozen dataclasses).

The HTTP contracts (Pydantic, ``api/schemas.py``) validate and serialize at the edge; routers
translate them to these commands and return these results. Application code never imports ``api``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# --- WhatsApp ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class WhatsAppConfigCommand:
    phone_number_id: str
    business_account_id: str | None = None
    display_phone_number: str | None = None
    default_language: str = "es"
    status: str = "active"
    access_token: str | None = None
    webhook_verify_token: str | None = None


@dataclass(frozen=True)
class WhatsAppConfigView:
    status: str
    has_secret: bool
    provider: str = "whatsapp_cloud"
    phone_number_id: str | None = None
    business_account_id: str | None = None
    display_phone_number: str | None = None
    default_language: str = "es"
    has_webhook_secret: bool = False
    voice_calling_enabled: bool = False
    last_health_check_at: datetime | None = None
    last_error_message: str | None = None


@dataclass(frozen=True)
class WhatsAppConnectionTestResult:
    status: str
    message: str | None = None
    sends_message: bool = False
    error_message: str | None = None


@dataclass(frozen=True)
class WhatsAppTemplateSyncReport:
    status: str
    fetched_count: int = 0
    approved_count: int = 0
    synced_count: int = 0
    ignored_count: int = 0
    error_message: str | None = None


@dataclass(frozen=True)
class WhatsAppTemplateSubmitResult:
    status: str
    meta_status: str | None = None
    provider_template_id: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class WhatsAppTemplateButton:
    type: str
    text: str
    url: str | None = None
    phone_number: str | None = None
    flow_id: str | None = None
    flow_action: str | None = None
    navigate_screen: str | None = None

    def to_meta_dict(self) -> dict[str, str]:
        return {key: value for key, value in self.__dict__.items() if value is not None}


@dataclass(frozen=True)
class WhatsAppTemplateCreateCommand:
    template_key: str
    name: str
    category: str
    body: str
    language: str = "es"
    header_text: str | None = None
    footer_text: str | None = None
    buttons: tuple[WhatsAppTemplateButton, ...] = ()


@dataclass(frozen=True)
class WhatsAppTemplateUpdateCommand:
    """Fields left as ``None`` are not changed (``buttons=None`` keeps the current buttons)."""

    name: str | None = None
    header_text: str | None = None
    body: str | None = None
    footer_text: str | None = None
    buttons: tuple[WhatsAppTemplateButton, ...] | None = None


@dataclass(frozen=True)
class WhatsAppTestMessageCommand:
    to_phone: str
    template_key: str | None = None
    provider_template_name: str | None = None
    language: str | None = None
    variables: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class WhatsAppTestMessageResult:
    status: str
    whatsapp_message_id: str | None = None
    provider_message_id: str | None = None
    template_key: str | None = None
    to_phone_masked: str | None = None
    message: str | None = None
    error_message: str | None = None


# --- Chatwoot ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ChatwootConfigCommand:
    account_id: int
    base_url: str = "https://crm.serviglobal-ia.com"
    default_inbox_id: int | None = None
    status: str = "active"
    api_token: str | None = None


@dataclass(frozen=True)
class ChatwootConfigView:
    status: str
    has_secret: bool
    provider: str = "chatwoot"
    mode: str = "external"
    base_url: str | None = None
    account_id: int | None = None
    account_name: str | None = None
    default_inbox_id: int | None = None
    default_inbox_name: str | None = None
    webhook_url: str | None = None
    last_health_check_at: datetime | None = None
    last_error_message: str | None = None


@dataclass(frozen=True)
class ChatwootTestResult:
    status: str
    error_message: str | None = None


@dataclass(frozen=True)
class ChatwootInboxView:
    id: int
    name: str
    channel_type: str | None = None


@dataclass(frozen=True)
class ChatwootTeamView:
    id: int
    name: str


@dataclass(frozen=True)
class ChatwootAgentView:
    id: int
    name: str
    email: str
    role: str
    confirmed: bool = True
