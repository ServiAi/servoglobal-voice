from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.modules.notifications.infrastructure.models import NotificationDelivery
from app.modules.integrations.public import find_whatsapp_delivery_evidence
from app.modules.notifications.public import NotificationDeliveryEvidence
from app.modules.notifications.ports import DeliveryEvidencePort
from app.modules.notifications.application.retry_policy import NotificationRetryPolicy

_UNSENT_MESSAGE_ERROR = "worker_claim_expired_before_send"
_MANUAL_REVIEW_ERROR = "whatsapp_send_outcome_unknown"


@dataclass(frozen=True)
class NotificationRecoveryOutcome:
    tenant_id: str
    delivery_id: str
    action: str  # sent | delivered | read | manual_review | retry | dead_letter


class NotificationDeliveryRecoveryService:
    """Reconciles abandoned `processing` deliveries against channel evidence.

    Never calls the WhatsApp provider: it only reads what was already
    recorded locally and decides whether to trust it as sent evidence, retry,
    or flag for manual review.
    """

    def __init__(
        self,
        db: Session,
        *,
        retry_policy: NotificationRetryPolicy,
        evidence_port: DeliveryEvidencePort | None = None,
    ) -> None:
        self.db = db
        self.retry_policy = retry_policy
        self.evidence_port = evidence_port or _IntegrationsDeliveryEvidence()

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
        try:
            outcomes = [
                self._recover_one(delivery, now=now, max_attempts=max_attempts) for delivery in deliveries
            ]
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return outcomes

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
                commit=False,
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
                commit=False,
            )
            return NotificationRecoveryOutcome(delivery.tenant_id, delivery.id, decision.action)

        decision = self.retry_policy.apply_failure(
            tenant_id=delivery.tenant_id,
            delivery_id=delivery.id,
            now=now,
            error_code=_UNSENT_MESSAGE_ERROR,
            retryable=True,
            max_attempts=max_attempts,
            commit=False,
        )
        return NotificationRecoveryOutcome(delivery.tenant_id, delivery.id, decision.action)

    def _find_message(self, delivery: NotificationDelivery) -> NotificationDeliveryEvidence | None:
        metadata = delivery.metadata_json or {}
        fallback_id = metadata.get("crm_whatsapp_message_id")
        return self.evidence_port.find_delivery_evidence(
            tenant_id=delivery.tenant_id,
            delivery_id=delivery.id,
            fallback_message_id=fallback_id if isinstance(fallback_id, str) else None,
        )

    def _sync_terminal(
        self,
        delivery: NotificationDelivery,
        *,
        status: str,
        message: NotificationDeliveryEvidence,
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

    def _manual_review(self, delivery: NotificationDelivery) -> None:
        delivery.status = "manual_review"
        delivery.error_message = _MANUAL_REVIEW_ERROR
        delivery.next_attempt_at = None
        delivery.claim_token = None
        delivery.claimed_at = None
        delivery.claim_expires_at = None
        self.db.add(delivery)


class _IntegrationsDeliveryEvidence:
    def find_delivery_evidence(
        self, *, tenant_id: str, delivery_id: str, fallback_message_id: str | None = None
    ) -> NotificationDeliveryEvidence | None:
        evidence = find_whatsapp_delivery_evidence(
            tenant_id=tenant_id,
            delivery_id=delivery_id,
            fallback_message_id=fallback_message_id,
        )
        if evidence is None:
            return None
        return NotificationDeliveryEvidence(
            id=evidence.id,
            status=evidence.status,
            provider_message_id=evidence.provider_message_id,
            sent_at=evidence.sent_at,
            delivered_at=evidence.delivered_at,
            read_at=evidence.read_at,
            created_at=evidence.created_at,
        )
