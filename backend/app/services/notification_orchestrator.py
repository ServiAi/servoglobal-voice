from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.notification_rules import (
    NotificationConditionEvaluationError,
    NotificationEventProcessingError,
    NotificationRecipientResolutionError,
    NotificationRuleConfigurationError,
    validate_notification_rule,
)
from app.models.notifications import DomainEvent, NotificationDelivery, TenantNotificationRule
from app.services.notification_capability_service import NotificationCapabilityService
from app.services.notification_condition_service import NotificationConditionService
from app.services.notification_recipient_service import NotificationRecipientService
from app.services.notification_rule_service import NotificationRuleService


@dataclass(frozen=True)
class NotificationPlanResult:
    event: DomainEvent
    deliveries: list[NotificationDelivery]
    created_count: int
    existing_count: int
    skipped_rule_count: int


class NotificationOrchestrator:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._capability_service = NotificationCapabilityService(db)
        self._rule_service = NotificationRuleService(db)
        self._condition_service = NotificationConditionService()
        self._recipient_service = NotificationRecipientService(db)

    def plan_event(
        self,
        *,
        tenant_id: str,
        event_id: str,
        now: datetime | None = None,
    ) -> NotificationPlanResult:
        current_time = self._resolve_now(now)

        event = self._get_event(tenant_id=tenant_id, event_id=event_id)

        if event.status == "processed":
            deliveries = self._list_event_deliveries(tenant_id=tenant_id, event_id=event.id)
            return NotificationPlanResult(
                event=event,
                deliveries=deliveries,
                created_count=0,
                existing_count=len(deliveries),
                skipped_rule_count=0,
            )

        if event.status == "processing":
            raise NotificationEventProcessingError(
                tenant_id=tenant_id, event_id=event_id, code="event_already_processing"
            )

        event.status = "processing"
        event.attempts += 1
        event.last_error = None
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)

        try:
            deliveries, created_count, existing_count, skipped_rule_count = self._plan_deliveries(
                tenant_id=tenant_id, event=event, now=current_time
            )
        except Exception as exc:  # noqa: BLE001 - deliberately broad to mark event failed safely
            self.db.rollback()
            failed_event = self._get_event(tenant_id=tenant_id, event_id=event_id)
            failed_event.status = "failed"
            failed_event.last_error = self._safe_error_code(exc)
            self.db.add(failed_event)
            self.db.commit()
            raise

        event.status = "processed"
        event.processed_at = current_time
        event.last_error = None
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)

        return NotificationPlanResult(
            event=event,
            deliveries=deliveries,
            created_count=created_count,
            existing_count=existing_count,
            skipped_rule_count=skipped_rule_count,
        )

    def _plan_deliveries(
        self, *, tenant_id: str, event: DomainEvent, now: datetime
    ) -> tuple[list[NotificationDelivery], int, int, int]:
        rules = self._rule_service.get_active_rules(tenant_id=tenant_id, event_type=event.event_type)

        deliveries: list[NotificationDelivery] = []
        created_count = 0
        existing_count = 0
        skipped_rule_count = 0

        for rule in rules:
            conditions = validate_notification_rule(rule)

            if not self._capability_service.is_enabled(
                tenant_id=tenant_id, capability_key=rule.capability_key
            ):
                skipped_rule_count += 1
                continue

            if not self._condition_service.matches(
                conditions=conditions,
                payload=event.payload_json,
                mode=rule.conditions_mode,
            ):
                skipped_rule_count += 1
                continue

            recipients = self._recipient_service.resolve(
                tenant_id=tenant_id, rule=rule, payload=event.payload_json
            )
            if not recipients:
                skipped_rule_count += 1
                continue

            scheduled_for, delivery_status, metadata = self._resolve_schedule(
                rule=rule, event=event, now=now
            )

            for recipient in recipients:
                delivery, created = self._get_or_create_delivery(
                    tenant_id=tenant_id,
                    event=event,
                    rule=rule,
                    recipient=recipient,
                    scheduled_for=scheduled_for,
                    status=delivery_status,
                    metadata=metadata,
                )
                deliveries.append(delivery)
                if created:
                    created_count += 1
                else:
                    existing_count += 1

        return deliveries, created_count, existing_count, skipped_rule_count

    def _resolve_schedule(
        self, *, rule: TenantNotificationRule, event: DomainEvent, now: datetime
    ) -> tuple[datetime, str, dict]:
        if rule.schedule_mode == "immediate":
            return max(now, self._ensure_utc_aware(event.available_at)), "pending", {}

        payload = event.payload_json if isinstance(event.payload_json, dict) else {}
        booking = payload.get("booking") if isinstance(payload, dict) else None
        start_at_raw = booking.get("start_at") if isinstance(booking, dict) else None

        if not isinstance(start_at_raw, str):
            raise NotificationRuleConfigurationError(
                tenant_id=rule.tenant_id, rule_id=rule.id, code="booking_start_at_missing"
            )
        try:
            booking_start_at = datetime.fromisoformat(start_at_raw)
        except ValueError:
            raise NotificationRuleConfigurationError(
                tenant_id=rule.tenant_id, rule_id=rule.id, code="booking_start_at_invalid"
            ) from None
        if booking_start_at.tzinfo is None or booking_start_at.tzinfo.utcoffset(booking_start_at) is None:
            raise NotificationRuleConfigurationError(
                tenant_id=rule.tenant_id, rule_id=rule.id, code="booking_start_at_naive"
            )

        scheduled_for = booking_start_at + timedelta(minutes=rule.schedule_offset_minutes)
        if scheduled_for < now:
            return (
                scheduled_for,
                "skipped",
                {
                    "reason": "scheduled_time_elapsed",
                    "action_type": rule.action_type,
                    "schedule_mode": rule.schedule_mode,
                },
            )
        return scheduled_for, "pending", {}

    def _get_or_create_delivery(
        self,
        *,
        tenant_id: str,
        event: DomainEvent,
        rule: TenantNotificationRule,
        recipient: str,
        scheduled_for: datetime,
        status: str,
        metadata: dict,
    ) -> tuple[NotificationDelivery, bool]:
        idempotency_key = self._build_idempotency_key(
            event_id=event.id, rule_id=rule.id, channel=rule.channel, recipient=recipient
        )

        existing = self._get_delivery_by_key(tenant_id=tenant_id, idempotency_key=idempotency_key)
        if existing is not None:
            return self._reconcile_delivery(existing, event=event, rule=rule, recipient=recipient), False

        delivery = NotificationDelivery(
            tenant_id=tenant_id,
            domain_event_id=event.id,
            notification_rule_id=rule.id,
            channel=rule.channel,
            recipient=recipient,
            template_key=rule.template_key,
            status=status,
            scheduled_for=scheduled_for,
            attempts=0,
            idempotency_key=idempotency_key,
            metadata_json=metadata,
            next_attempt_at=scheduled_for if status == "pending" else None,
        )
        self.db.add(delivery)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self._get_delivery_by_key(tenant_id=tenant_id, idempotency_key=idempotency_key)
            if existing is not None:
                return (
                    self._reconcile_delivery(existing, event=event, rule=rule, recipient=recipient),
                    False,
                )
            raise

        self.db.refresh(delivery)
        return delivery, True

    def _reconcile_delivery(
        self,
        existing: NotificationDelivery,
        *,
        event: DomainEvent,
        rule: TenantNotificationRule,
        recipient: str,
    ) -> NotificationDelivery:
        if (
            existing.domain_event_id == event.id
            and existing.notification_rule_id == rule.id
            and existing.channel == rule.channel
            and existing.recipient == recipient
            and existing.template_key == rule.template_key
        ):
            if existing.status == "pending" and existing.next_attempt_at is None:
                existing.next_attempt_at = existing.scheduled_for
                self.db.add(existing)
                self.db.commit()
                self.db.refresh(existing)
            return existing
        raise NotificationEventProcessingError(
            tenant_id=existing.tenant_id, event_id=event.id, code="delivery_idempotency_conflict"
        )

    def _get_delivery_by_key(
        self, *, tenant_id: str, idempotency_key: str
    ) -> NotificationDelivery | None:
        return (
            self.db.query(NotificationDelivery)
            .filter(
                NotificationDelivery.tenant_id == tenant_id,
                NotificationDelivery.idempotency_key == idempotency_key,
            )
            .first()
        )

    def _get_event(self, *, tenant_id: str, event_id: str) -> DomainEvent:
        event = (
            self.db.query(DomainEvent)
            .filter(DomainEvent.tenant_id == tenant_id, DomainEvent.id == event_id)
            .first()
        )
        if event is None:
            raise NotificationEventProcessingError(
                tenant_id=tenant_id, event_id=event_id, code="event_not_found"
            )
        return event

    def _list_event_deliveries(
        self, *, tenant_id: str, event_id: str
    ) -> list[NotificationDelivery]:
        return (
            self.db.query(NotificationDelivery)
            .filter(
                NotificationDelivery.tenant_id == tenant_id,
                NotificationDelivery.domain_event_id == event_id,
            )
            .order_by(NotificationDelivery.created_at.asc(), NotificationDelivery.id.asc())
            .all()
        )

    @staticmethod
    def _build_idempotency_key(*, event_id: str, rule_id: str, channel: str, recipient: str) -> str:
        digest = hashlib.sha256(f"{channel}:{recipient}".encode("utf-8")).hexdigest()
        return f"event:{event_id}:rule:{rule_id}:recipient:{digest}"

    @staticmethod
    def _safe_error_code(exc: Exception) -> str:
        if isinstance(
            exc,
            (
                NotificationRuleConfigurationError,
                NotificationConditionEvaluationError,
                NotificationRecipientResolutionError,
                NotificationEventProcessingError,
            ),
        ):
            return exc.code
        return type(exc).__name__

    @staticmethod
    def _ensure_utc_aware(value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @staticmethod
    def _resolve_now(now: datetime | None) -> datetime:
        current = now if now is not None else datetime.now(timezone.utc)
        if current.tzinfo is None or current.tzinfo.utcoffset(current) is None:
            raise ValueError("now must be timezone-aware")
        return current
