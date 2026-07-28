from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.domain.notification_delivery_state import CLAIMABLE_STATUSES
from app.models.notifications import NotificationDelivery


@dataclass(frozen=True)
class NotificationDeliveryClaim:
    tenant_id: str
    delivery_id: str
    claim_token: str
    attempts: int
    claimed_at: datetime
    claim_expires_at: datetime


def _ensure_aware(now: datetime) -> None:
    if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
        raise ValueError("now must be timezone-aware")


class NotificationDeliveryClaimService:
    """Claims due WhatsApp deliveries atomically using SELECT ... FOR UPDATE SKIP LOCKED.

    No HTTP call to a provider is ever made while holding this lock: claims
    are committed immediately and delivery execution happens afterwards in a
    separate transaction.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def build_batch_select(self, *, now: datetime, max_attempts: int, batch_size: int) -> Select:
        due_at = sa.func.coalesce(NotificationDelivery.next_attempt_at, NotificationDelivery.scheduled_for)
        return (
            select(NotificationDelivery)
            .where(
                NotificationDelivery.channel == "whatsapp",
                NotificationDelivery.status.in_(CLAIMABLE_STATUSES),
                NotificationDelivery.scheduled_for <= now,
                due_at <= now,
                NotificationDelivery.attempts < max_attempts,
            )
            .order_by(due_at.asc(), NotificationDelivery.scheduled_for.asc(), NotificationDelivery.created_at.asc(), NotificationDelivery.id.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )

    def claim_batch(
        self,
        *,
        now: datetime,
        lease_seconds: int,
        max_attempts: int,
        batch_size: int,
    ) -> list[NotificationDeliveryClaim]:
        _ensure_aware(now)
        query = self.build_batch_select(now=now, max_attempts=max_attempts, batch_size=batch_size)
        deliveries = self.db.execute(query).scalars().all()
        claims = [self._apply_claim(delivery, now=now, lease_seconds=lease_seconds) for delivery in deliveries]
        self.db.commit()
        return claims

    def claim_one(
        self,
        *,
        tenant_id: str,
        delivery_id: str,
        now: datetime,
        lease_seconds: int,
        max_attempts: int,
    ) -> NotificationDeliveryClaim | None:
        _ensure_aware(now)
        due_at = sa.func.coalesce(NotificationDelivery.next_attempt_at, NotificationDelivery.scheduled_for)
        query = (
            select(NotificationDelivery)
            .where(
                NotificationDelivery.tenant_id == tenant_id,
                NotificationDelivery.id == delivery_id,
                NotificationDelivery.channel == "whatsapp",
                NotificationDelivery.status.in_(CLAIMABLE_STATUSES),
                NotificationDelivery.scheduled_for <= now,
                due_at <= now,
                NotificationDelivery.attempts < max_attempts,
            )
            .with_for_update(skip_locked=True)
        )
        delivery = self.db.execute(query).scalars().first()
        if delivery is None:
            self.db.commit()
            return None
        claim = self._apply_claim(delivery, now=now, lease_seconds=lease_seconds)
        self.db.commit()
        return claim

    def _apply_claim(
        self, delivery: NotificationDelivery, *, now: datetime, lease_seconds: int
    ) -> NotificationDeliveryClaim:
        token = secrets.token_hex(16)
        expires_at = now + timedelta(seconds=lease_seconds)
        delivery.status = "processing"
        delivery.attempts += 1
        delivery.claim_token = token
        delivery.claimed_at = now
        delivery.claim_expires_at = expires_at
        delivery.next_attempt_at = expires_at
        delivery.error_message = None
        self.db.add(delivery)
        self.db.flush()
        return NotificationDeliveryClaim(
            tenant_id=delivery.tenant_id,
            delivery_id=delivery.id,
            claim_token=token,
            attempts=delivery.attempts,
            claimed_at=now,
            claim_expires_at=expires_at,
        )
