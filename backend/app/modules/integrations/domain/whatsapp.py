"""WhatsApp pure helpers and value objects."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

WHATSAPP_BUSINESS_CALLING_FEATURE = "whatsapp_business_calling"
MISSING_PROVIDER_MESSAGE_ID_ERROR = "whatsapp_provider_message_id_missing"

# Meta delivery progress; a status may only move forward (a late "delivered" never undoes "read").
STATUS_RANK = {"queued": 0, "sent": 1, "delivered": 2, "read": 3}


@dataclass(frozen=True)
class WhatsAppClientConfig:
    access_token: str
    phone_number_id: str


def sanitize_whatsapp_error(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer [REDACTED]", value)
    text = re.sub(r"EA[A-Za-z0-9]{20,}", "[REDACTED_TOKEN]", text)
    text = re.sub(r"\+?\d[\d\s().-]{6,}\d", "[REDACTED_PHONE]", text)
    text = re.sub(r"[\w.\-+]+@[\w.\-]+\.\w+", "[REDACTED_EMAIL]", text)
    return text[:500]


def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    return digits or None


def safe_preview(value: str | None) -> str | None:
    if value is None:
        return None
    return value.replace("\r", " ").replace("\n", " ")[:240]


def mask_phone(phone: str) -> str:
    digits = normalize_phone(phone) or ""
    return f"***{digits[-4:]}" if len(digits) > 4 else "***"


def extract_provider_message_id(payload: dict[str, Any]) -> str | None:
    messages = payload.get("messages")
    if isinstance(messages, list) and messages and isinstance(messages[0], dict):
        value = messages[0].get("id")
        return value if isinstance(value, str) else None
    return None


def can_advance_status(current: str | None, new: str) -> bool:
    """True unless ``new`` would move a delivered/read message backwards.

    Unknown statuses (``failed``, ``received``...) are always accepted, as before."""
    if current in STATUS_RANK and new in STATUS_RANK:
        return STATUS_RANK[new] >= STATUS_RANK[current]
    return True


@dataclass(frozen=True)
class WhatsAppStatusUpdate:
    """A delivery status reported by the provider for a message we sent."""

    phone_number_id: str | None
    provider_message_id: str | None
    status: str | None
    error: str | None = None


@dataclass(frozen=True)
class WhatsAppInboundMessage:
    """A message a contact sent to the tenant's number."""

    phone_number_id: str | None
    from_phone: str | None
    provider_message_id: str | None
    body: str | None = None


WhatsAppWebhookEvent = WhatsAppStatusUpdate | WhatsAppInboundMessage
