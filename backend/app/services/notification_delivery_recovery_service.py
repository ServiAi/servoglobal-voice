from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.crm import CrmWhatsAppMessage
from app.models.notifications import NotificationDelivery
from app.services.notification_retry_policy import NotificationRetryPolicy

_UNSENT_MESSAGE_ERROR = "worker_claim_expired_before_send"
_MANUAL_REVIEW_ERROR = "whatsapp_send_outcome_unknown"


@dataclass(frozen=True)
class NotificationRecoveryOutcome:
    tenant_id: str
    delivery_id: str
    action: str  # sent | delivered | read | manual_review | retry | dead_letter


class NotificationDeliveryRecoveryService:
    """Reconciles abandoned `processing` deliveries against CrmWhatsAppMessage.

    Never calls the WhatsApp provider: it only reads what was already
    recorded locally and decides whether to trust it as sent evidence, retry,
    or flag for manual review.
    """

    def __init__(self, db: Session, *, retry_policy: NotificationRetryPolicy) -> None:
        self.db = db
        self.retry_policy = retry_policy

    def recover_batch(
        self,
        *,
        now: datetime,
        legacy_stale_seconds: int,
        max_attempts: int,
        batch_size: int,
    ) -> list[NotificationRecoveryOutcome]:
        if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
            raise ValueError("now must be timezone-aware")

        legacy_cutoff = now - timedelta(seconds=legacy_stale_seconds)
        query = (
            select(NotificationDelivery)
            .where(
                NotificationDelivery.status == "processing",
                or_(
                    and_(
                        NotificationDelivery.claim_expires_at.isnot(None),
                        NotificationDelivery.claim_expires_at <= now,
                    ),
                    and_(
                        NotificationDelivery.claim_expires_at.is_(None),
                        NotificationDelivery.updated_at <= legacy_cutoff,
                    ),
                ),
            )
            .order_by(NotificationDelivery.updated_at.asc(), NotificationDelivery.id.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        deliveries = self.db.execute(query).scalars().all()
        return [self._recover_one(delivery, now=now, max_attempts=max_attempts) for delivery in deliveries]

    def _recover_one(
        self, delivery: NotificationDelivery, *, now: datetime, max_attempts: int
    ) -> NotificationRecoveryOutcome:
        message = self._find_message(delivery)

        if message is None:
            decision = self.retry_policy.apply_failure(
                tenant_id=delivery.tenant_id,
                delivery_id=delivery.id,
                now=now,
                error_code=_UNSENT_MESSAGE_ERROR,
                retryable=True,
                max_attempts=max_attempts,
            )
            return NotificationRecoveryOutcome(delivery.tenant_id, delivery.id, decision.action)

        status = message.status

        if status == "read":
            self._sync_terminal(delivery, status="read", message=message, now=now)
            return NotificationRecoveryOutcome(delivery.tenant_id, delivery.id, "read")
        if status == "delivered":
            self._sync_terminal(delivery, status="delivered", message=message, now=now)
            return NotificationRecoveryOutcome(delivery.tenant_id, delivery.id, "delivered")
        if status == "sent":
            self._sync_terminal(delivery, status="sent", message=message, now=now)
            return NotificationRecoveryOutcome(delivery.tenant_id, delivery.id, "sent")
        if status == "queued" and message.provider_message_id:
            self._sync_terminal(delivery, status="sent", message=message, now=now)
            return NotificationRecoveryOutcome(delivery.tenant_id, delivery.id, "sent")
        if status == "queued":
            self._manual_review(delivery)
            return NotificationRecoveryOutcome(delivery.tenant_id, delivery.id, "manual_review")
        if status == "failed":
            decision = self.retry_policy.apply_failure(
                tenant_id=delivery.tenant_id,
                delivery_id=delivery.id,
                now=now,
                error_code="whatsapp_provider_send_failed",
                retryable=True,
                max_attempts=max_attempts,
            )
            return NotificationRecoveryOutcome(delivery.tenant_id, delivery.id, decision.action)

        decision = self.retry_policy.apply_failure(
            tenant_id=delivery.tenant_id,
            delivery_id=delivery.id,
            now=now,
            error_code=_UNSENT_MESSAGE_ERROR,
            retryable=True,
            max_attempts=max_attempts,
        )
        return NotificationRecoveryOutcome(delivery.tenant_id, delivery.id, decision.action)

    def _find_message(self, delivery: NotificationDelivery) -> CrmWhatsAppMessage | None:
        message = self.db.scalar(
            select(CrmWhatsAppMessage)
            .where(
                CrmWhatsAppMessage.tenant_id == delivery.tenant_id,
                CrmWhatsAppMessage.notification_delivery_id == delivery.id,
            )
            .order_by(CrmWhatsAppMessage.created_at.desc(), CrmWhatsAppMessage.id.desc())
        )
        if message is not None:
            return message

        metadata = delivery.metadata_json or {}
        fallback_id = metadata.get("crm_whatsapp_message_id")
        if not fallback_id:
            return None
        return self.db.scalar(
            select(CrmWhatsAppMessage).where(
                CrmWhatsAppMessage.tenant_id == delivery.tenant_id,
                CrmWhatsAppMessage.id == fallback_id,
            )
        )

    def _sync_terminal(
        self,
        delivery: NotificationDelivery,
        *,
        status: str,
        message: CrmWhatsAppMessage,
        now: datetime,
    ) -> None:
        delivery.status = status
        delivery.provider_message_id = message.provider_message_id or delivery.provider_message_id
        if status in ("sent", "delivered", "read"):
            delivery.sent_at = message.sent_at or delivery.sent_at or message.created_at or now
        if status in ("delivered", "read"):
            delivery.delivered_at = message.delivered_at or delivery.delivered_at or delivery.sent_at
        if status == "read":
            delivery.read_at = message.read_at or delivery.read_at or now
        delivery.next_attempt_at = None
        delivery.error_message = None
        delivery.claim_token = None
        delivery.claimed_at = None
        delivery.claim_expires_at = None
        self.db.add(delivery)
        self.db.commit()

    def _manual_review(self, delivery: NotificationDelivery) -> None:
        delivery.status = "manual_review"
        delivery.error_message = _MANUAL_REVIEW_ERROR
        delivery.next_attempt_at = None
        delivery.claim_token = None
        delivery.claimed_at = None
        delivery.claim_expires_at = None
        self.db.add(delivery)
        self.db.commit()
