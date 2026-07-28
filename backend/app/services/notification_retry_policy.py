from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.notification_delivery_state import NON_RETRYABLE_ERROR_CODES
from app.models.notifications import NotificationDelivery


@dataclass(frozen=True)
class NotificationRetryDecision:
    action: str  # retry | dead_letter | manual_review
    next_attempt_at: datetime | None
    status: str
    error_code: str


class NotificationRetryPolicy:
    def __init__(
        self,
        db: Session,
        *,
        base_retry_seconds: int,
        max_retry_seconds: int,
        jitter_seconds: int,
        jitter_fn: Callable[[], float] | None = None,
    ) -> None:
        self.db = db
        self.base_retry_seconds = base_retry_seconds
        self.max_retry_seconds = max_retry_seconds
        self.jitter_seconds = jitter_seconds
        self._jitter_fn = jitter_fn or (lambda: random.uniform(0, jitter_seconds) if jitter_seconds else 0.0)

    def compute_delay_seconds(self, *, attempts: int) -> float:
        delay = self.base_retry_seconds * (2 ** max(attempts - 1, 0))
        delay = min(delay, self.max_retry_seconds)
        jitter = self._jitter_fn()
        jitter = max(0.0, min(jitter, self.jitter_seconds))
        return delay + jitter

    def apply_failure(
        self,
        *,
        tenant_id: str,
        delivery_id: str,
        now: datetime,
        error_code: str,
        retryable: bool,
        max_attempts: int,
    ) -> NotificationRetryDecision:
        if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
            raise ValueError("now must be timezone-aware")

        delivery = self.db.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.tenant_id == tenant_id,
                NotificationDelivery.id == delivery_id,
            )
        )
        if delivery is None:
            raise ValueError("delivery_not_found")

        permanent = (not retryable) or error_code in NON_RETRYABLE_ERROR_CODES
        exhausted = delivery.attempts >= max_attempts

        if permanent:
            decision = NotificationRetryDecision(
                action="dead_letter", next_attempt_at=None, status="dead_letter", error_code=error_code
            )
        elif exhausted:
            decision = NotificationRetryDecision(
                action="dead_letter",
                next_attempt_at=None,
                status="dead_letter",
                error_code="retry_attempts_exhausted",
            )
        else:
            delay = self.compute_delay_seconds(attempts=delivery.attempts)
            decision = NotificationRetryDecision(
                action="retry",
                next_attempt_at=now + timedelta(seconds=delay),
                status="failed",
                error_code=error_code,
            )

        delivery.status = decision.status
        delivery.next_attempt_at = decision.next_attempt_at
        delivery.error_message = decision.error_code
        delivery.failed_at = now
        delivery.claim_token = None
        delivery.claimed_at = None
        delivery.claim_expires_at = None
        self.db.add(delivery)
        self.db.commit()
        return decision
