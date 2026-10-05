"""Lookup of the message ledger row that proves what happened to a notification delivery."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.integrations.infrastructure.models import CrmWhatsAppMessage


def find_delivery_message(
    db: Session, *, tenant_id: str, delivery_id: str, fallback_message_id: str | None = None
) -> CrmWhatsAppMessage | None:
    message = db.scalar(
        select(CrmWhatsAppMessage)
        .where(
            CrmWhatsAppMessage.tenant_id == tenant_id,
            CrmWhatsAppMessage.notification_delivery_id == delivery_id,
        )
        .order_by(CrmWhatsAppMessage.created_at.desc(), CrmWhatsAppMessage.id.desc())
    )
    if message is None and fallback_message_id:
        message = db.scalar(
            select(CrmWhatsAppMessage).where(
                CrmWhatsAppMessage.tenant_id == tenant_id,
                CrmWhatsAppMessage.id == fallback_message_id,
            )
        )
    return message
