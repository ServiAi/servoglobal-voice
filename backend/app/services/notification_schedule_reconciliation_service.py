from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notifications import DomainEvent, NotificationDelivery

_RELEVANT_EVENT_TYPES = {"booking.cancelled", "booking.rescheduled"}
_CANCELLABLE_STATUSES = {"pending", "failed"}
_SUPERSEDED_BY_RESCHEDULE_TYPES = {"booking.created", "booking.rescheduled"}


@dataclass(frozen=True)
class NotificationScheduleReconciliationResult:
    status: str  # applied | not_applicable | error
    cancelled_count: int
    flagged_count: int
    error_code: str | None = None


class NotificationScheduleReconciliationService:
    """Cancels or flags-for-cancellation stale reminder deliveries when a
    booking is cancelled or rescheduled. Never raises: a reconciliation
    failure must not break the booking webhook that triggered it.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def reconcile_for_event(
        self, *, tenant_id: str, event_id: str, now: datetime
    ) -> NotificationScheduleReconciliationResult:
        try:
            event = self.db.scalar(
                select(DomainEvent).where(DomainEvent.tenant_id == tenant_id, DomainEvent.id == event_id)
            )
            if event is None or event.event_type not in _RELEVANT_EVENT_TYPES:
                return NotificationScheduleReconciliationResult(
                    status="not_applicable", cancelled_count=0, flagged_count=0
                )
            if event.resource_type != "crm_booking" or not event.resource_id:
                return NotificationScheduleReconciliationResult(
                    status="not_applicable", cancelled_count=0, flagged_count=0
                )

            if event.event_type == "booking.cancelled":
                reason = "booking_cancelled"
                allowed_event_types: set[str] | None = None
            else:
                reason = "booking_schedule_superseded"
                allowed_event_types = _SUPERSEDED_BY_RESCHEDULE_TYPES

            prior_events = self._prior_events(
                tenant_id=tenant_id,
                resource_id=event.resource_id,
                before=event,
                allowed_event_types=allowed_event_types,
            )

            cancelled_count = 0
            flagged_count = 0
            for prior_event in prior_events:
                deliveries = self.db.scalars(
                    select(NotificationDelivery).where(
                        NotificationDelivery.tenant_id == tenant_id,
                        NotificationDelivery.domain_event_id == prior_event.id,
                    )
                ).all()
                for delivery in deliveries:
                    if delivery.status in _CANCELLABLE_STATUSES:
                        delivery.status = "cancelled"
                        delivery.next_attempt_at = None
                        delivery.error_message = reason
                        delivery.claim_token = None
                        delivery.claimed_at = None
                        delivery.claim_expires_at = None
                        self.db.add(delivery)
                        cancelled_count += 1
                    elif delivery.status == "processing":
                        metadata = dict(delivery.metadata_json or {})
                        if not metadata.get("cancel_requested"):
                            metadata["cancel_requested"] = True
                            metadata["cancel_reason"] = reason
                            delivery.metadata_json = metadata
                            self.db.add(delivery)
                            flagged_count += 1

            self.db.commit()
            return NotificationScheduleReconciliationResult(
                status="applied", cancelled_count=cancelled_count, flagged_count=flagged_count
            )
        except Exception as exc:  # noqa: BLE001 - reconciliation must never break the caller
            self.db.rollback()
            return NotificationScheduleReconciliationResult(
                status="error", cancelled_count=0, flagged_count=0, error_code=type(exc).__name__
            )

    def _prior_events(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        before: DomainEvent,
        allowed_event_types: set[str] | None,
    ) -> list[DomainEvent]:
        candidates = self.db.scalars(
            select(DomainEvent).where(
                DomainEvent.tenant_id == tenant_id,
                DomainEvent.resource_type == "crm_booking",
                DomainEvent.resource_id == resource_id,
                DomainEvent.id != before.id,
            )
        ).all()
        result = []
        for candidate in candidates:
            if not self._is_before(candidate, before):
                continue
            if allowed_event_types is not None and candidate.event_type not in allowed_event_types:
                continue
            result.append(candidate)
        return result

    @staticmethod
    def _is_before(a: DomainEvent, b: DomainEvent) -> bool:
        if a.created_at != b.created_at:
            return a.created_at < b.created_at
        return a.id < b.id
