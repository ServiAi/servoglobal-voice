from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notifications import NotificationDelivery
from app.services.whatsapp_client import sanitize_whatsapp_error

_ACCEPTED_STATUSES = {"sent", "delivered", "read", "failed"}
_STATUS_RANK = {"sent": 1, "delivered": 2, "read": 3}

# A `failed` webhook must never overwrite a confirmed outcome or interfere
# with a delivery currently owned by a different (newer) execution.
_FAILED_WEBHOOK_PROTECTED_STATUSES = {
    "sent",
    "delivered",
    "read",
    "skipped",
    "cancelled",
    "dead_letter",
    "processing",
}


class NotificationDeliveryStatusService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_delivery(self, *, tenant_id: str, delivery_id: str) -> NotificationDelivery | None:
        return self.db.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.tenant_id == tenant_id,
                NotificationDelivery.id == delivery_id,
            )
        )

    def get_by_provider_message_id(
        self, *, tenant_id: str, provider_message_id: str
    ) -> NotificationDelivery | None:
        return self.db.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.tenant_id == tenant_id,
                NotificationDelivery.provider_message_id == provider_message_id,
            )
        )

    def apply_provider_status(
        self,
        *,
        tenant_id: str,
        provider_message_id: str,
        status: str,
        occurred_at: datetime,
        error_message: str | None = None,
    ) -> NotificationDelivery | None:
        if status not in _ACCEPTED_STATUSES:
            return None

        delivery = self.get_by_provider_message_id(
            tenant_id=tenant_id, provider_message_id=provider_message_id
        )
        if delivery is None:
            return None

        if status == "failed":
            if delivery.status in _FAILED_WEBHOOK_PROTECTED_STATUSES:
                return delivery
            delivery.status = "failed"
            delivery.failed_at = occurred_at
            delivery.error_message = sanitize_whatsapp_error(error_message) if error_message else delivery.error_message
            delivery.claim_token = None
            delivery.claimed_at = None
            delivery.claim_expires_at = None
            self.db.add(delivery)
            return delivery

        current_rank = _STATUS_RANK.get(delivery.status, 0)
        new_rank = _STATUS_RANK[status]
        if new_rank < current_rank:
            return delivery

        delivery.status = status
        if status == "sent":
            delivery.sent_at = delivery.sent_at or occurred_at
        elif status == "delivered":
            delivery.delivered_at = occurred_at
        elif status == "read":
            delivery.read_at = occurred_at
            if delivery.delivered_at is None:
                delivery.delivered_at = occurred_at

        # A confirmed provider status is definitive: release any pending
        # claim/backoff so the worker never retries an already-delivered message.
        delivery.next_attempt_at = None
        delivery.claim_token = None
        delivery.claimed_at = None
        delivery.claim_expires_at = None
        delivery.error_message = None

        self.db.add(delivery)
        return delivery
