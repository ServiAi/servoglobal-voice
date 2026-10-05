"""Meta WhatsApp Cloud webhook payload -> provider-neutral events.

The only place that knows the shape of Meta's ``entry/changes/value`` envelope; the
application layer works with ``WhatsAppStatusUpdate`` / ``WhatsAppInboundMessage``.
"""

from __future__ import annotations

from typing import Any

from app.modules.integrations.domain.whatsapp import (
    WhatsAppInboundMessage,
    WhatsAppStatusUpdate,
    WhatsAppWebhookEvent,
)


def parse_webhook_payload(payload: dict[str, Any]) -> list[WhatsAppWebhookEvent]:
    events: list[WhatsAppWebhookEvent] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            phone_number_id = (value.get("metadata") or {}).get("phone_number_id")
            phone_number_id = str(phone_number_id) if phone_number_id else None
            for item in value.get("statuses") or []:
                errors = item.get("errors")
                events.append(
                    WhatsAppStatusUpdate(
                        phone_number_id=phone_number_id,
                        provider_message_id=item.get("id"),
                        status=item.get("status"),
                        error=str(errors) if errors else None,
                    )
                )
            for item in value.get("messages") or []:
                text = item.get("text")
                events.append(
                    WhatsAppInboundMessage(
                        phone_number_id=phone_number_id,
                        from_phone=item.get("from"),
                        provider_message_id=item.get("id"),
                        body=text.get("body") if isinstance(text, dict) else None,
                    )
                )
    return events
