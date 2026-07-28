from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.domain.events import _check_json_safe
from app.models.crm import CrmBooking, CrmContact, CrmLead, CrmVoiceCall
from app.models.notifications import DomainEvent
from app.services.domain_event_service import DomainEventIdempotencyConflictError, DomainEventService
from app.services.notification_orchestrator import NotificationOrchestrator
from app.services.notification_retry_policy import NotificationRetryPolicy
from app.services.notification_schedule_reconciliation_service import (
    NotificationScheduleReconciliationService,
)
from app.services.whatsapp_client import WhatsAppCloudClient
from app.services.whatsapp_notification_executor import WhatsAppNotificationExecutor

logger = logging.getLogger(__name__)

_BOOKING_EVENT_TYPES = {"booking.created", "booking.cancelled", "booking.rescheduled"}

_CALL_STATUS_EVENT_MAP = {
    "completed": "call.completed",
    "failed": "call.failed",
    "no_answer": "call.no_answer",
    "busy": "call.no_answer",
}

_CALL_IDEMPOTENCY_SUFFIX = {
    "call.completed": "completed",
    "call.failed": "failed",
    "call.no_answer": "no_answer",
}


@dataclass(frozen=True)
class NotificationEventPipelineResult:
    status: str
    event_id: str | None
    event_created: bool
    planned_delivery_count: int
    sent_count: int
    failed_count: int
    pending_count: int
    skipped_count: int
    error_code: str | None = None


class NotificationEventPipelineIdentityConflictError(RuntimeError):
    pass


def _safe_result(*, error_code: str) -> NotificationEventPipelineResult:
    return NotificationEventPipelineResult(
        status="failed",
        event_id=None,
        event_created=False,
        planned_delivery_count=0,
        sent_count=0,
        failed_count=0,
        pending_count=0,
        skipped_count=0,
        error_code=error_code,
    )


def _ignored_result(*, error_code: str) -> NotificationEventPipelineResult:
    return NotificationEventPipelineResult(
        status="ignored",
        event_id=None,
        event_created=False,
        planned_delivery_count=0,
        sent_count=0,
        failed_count=0,
        pending_count=0,
        skipped_count=0,
        error_code=error_code,
    )


class NotificationEventPipeline:
    def __init__(self, db: Session, whatsapp_client: WhatsAppCloudClient | None = None) -> None:
        self.db = db
        self._whatsapp_client = whatsapp_client
        self._domain_events = DomainEventService(db)
        self._orchestrator = NotificationOrchestrator(db)
        self._schedule_reconciliation = NotificationScheduleReconciliationService(db)

    # ------------------------------------------------------------------
    # Booking events
    # ------------------------------------------------------------------
    def process_booking_event(
        self,
        *,
        tenant_id: str,
        booking_id: str,
        event_type: str,
        now: datetime | None = None,
    ) -> NotificationEventPipelineResult:
        try:
            current_time = self._resolve_now(now)

            if event_type not in _BOOKING_EVENT_TYPES:
                return _safe_result(error_code="unsupported_booking_event_type")

            booking = self.db.scalar(
                select(CrmBooking).where(CrmBooking.tenant_id == tenant_id, CrmBooking.id == booking_id)
            )
            if booking is None:
                return _safe_result(error_code="booking_not_found")

            payload = self._booking_payload(tenant_id=tenant_id, booking=booking)
            idempotency_key = self._booking_idempotency_key(booking=booking, event_type=event_type)

            try:
                event, created = self._publish_or_reuse_event(
                    tenant_id=tenant_id,
                    event_type=event_type,
                    source="crm_booking",
                    idempotency_key=idempotency_key,
                    payload=payload,
                    resource_type="crm_booking",
                    resource_id=booking.id,
                    correlation_id=booking.provider_booking_uid or booking.provider_booking_id,
                    available_at=current_time,
                )
            except NotificationEventPipelineIdentityConflictError:
                self.db.rollback()
                return _safe_result(error_code="domain_event_identity_conflict")

            self._schedule_reconciliation.reconcile_for_event(
                tenant_id=tenant_id, event_id=event.id, now=current_time
            )

            return self._plan_and_execute(
                tenant_id=tenant_id, event=event, event_created=created, now=current_time
            )
        except Exception as exc:  # noqa: BLE001 - notifications must never break the caller
            self.db.rollback()
            self._log_safe_error(tenant_id=tenant_id, resource_id=booking_id, exc=exc)
            return _safe_result(error_code="booking_event_processing_error")

    # ------------------------------------------------------------------
    # Call events
    # ------------------------------------------------------------------
    def process_call_event(
        self,
        *,
        tenant_id: str,
        voice_call_id: str,
        now: datetime | None = None,
    ) -> NotificationEventPipelineResult:
        try:
            current_time = self._resolve_now(now)

            call = self.db.scalar(
                select(CrmVoiceCall).where(
                    CrmVoiceCall.tenant_id == tenant_id, CrmVoiceCall.id == voice_call_id
                )
            )
            if call is None:
                return _safe_result(error_code="voice_call_not_found")

            event_type = _CALL_STATUS_EVENT_MAP.get(call.status)
            if event_type is None:
                return _ignored_result(error_code="call_status_not_notifiable")

            payload = self._call_payload(tenant_id=tenant_id, call=call)
            idempotency_key = self._call_idempotency_key(call=call, event_type=event_type)

            try:
                event, created = self._publish_or_reuse_event(
                    tenant_id=tenant_id,
                    event_type=event_type,
                    source="crm_voice_call",
                    idempotency_key=idempotency_key,
                    payload=payload,
                    resource_type="crm_voice_call",
                    resource_id=call.id,
                    correlation_id=call.provider_call_id or call.provider_session_id,
                    available_at=current_time,
                )
            except NotificationEventPipelineIdentityConflictError:
                self.db.rollback()
                return _safe_result(error_code="domain_event_identity_conflict")

            self._schedule_reconciliation.reconcile_for_event(
                tenant_id=tenant_id, event_id=event.id, now=current_time
            )

            return self._plan_and_execute(
                tenant_id=tenant_id, event=event, event_created=created, now=current_time
            )
        except Exception as exc:  # noqa: BLE001 - notifications must never break the caller
            self.db.rollback()
            self._log_safe_error(tenant_id=tenant_id, resource_id=voice_call_id, exc=exc)
            return _safe_result(error_code="call_event_processing_error")

    # ------------------------------------------------------------------
    # Shared: publish/reuse, plan, immediate execution
    # ------------------------------------------------------------------
    def _publish_or_reuse_event(
        self,
        *,
        tenant_id: str,
        event_type: str,
        source: str,
        idempotency_key: str,
        payload: dict[str, Any],
        resource_type: str,
        resource_id: str,
        correlation_id: str | None,
        available_at: datetime,
    ) -> tuple[DomainEvent, bool]:
        existing = self._domain_events.get_by_idempotency_key(
            tenant_id=tenant_id, idempotency_key=idempotency_key
        )
        if existing is not None:
            if self._same_identity(
                existing, event_type=event_type, resource_type=resource_type, resource_id=resource_id
            ):
                return existing, False
            raise NotificationEventPipelineIdentityConflictError()

        try:
            result = self._domain_events.publish(
                tenant_id=tenant_id,
                event_type=event_type,
                source=source,
                idempotency_key=idempotency_key,
                payload=payload,
                resource_type=resource_type,
                resource_id=resource_id,
                correlation_id=correlation_id,
                available_at=available_at,
            )
        except DomainEventIdempotencyConflictError:
            existing = self._domain_events.get_by_idempotency_key(
                tenant_id=tenant_id, idempotency_key=idempotency_key
            )
            if existing is not None and self._same_identity(
                existing, event_type=event_type, resource_type=resource_type, resource_id=resource_id
            ):
                return existing, False
            raise NotificationEventPipelineIdentityConflictError() from None

        return result.event, result.created

    def _plan_and_execute(
        self, *, tenant_id: str, event: DomainEvent, event_created: bool, now: datetime
    ) -> NotificationEventPipelineResult:
        try:
            plan_result = self._orchestrator.plan_event(tenant_id=tenant_id, event_id=event.id, now=now)
        except Exception as exc:  # noqa: BLE001 - planning failures must stay a safe result
            self.db.rollback()
            self._log_safe_error(tenant_id=tenant_id, resource_id=event.resource_id or event.id, exc=exc)
            return NotificationEventPipelineResult(
                status="failed",
                event_id=event.id,
                event_created=event_created,
                planned_delivery_count=0,
                sent_count=0,
                failed_count=0,
                pending_count=0,
                skipped_count=0,
                error_code="notification_planning_failed",
            )

        executor = WhatsAppNotificationExecutor(self.db, client=self._whatsapp_client)
        retry_policy = NotificationRetryPolicy(
            self.db,
            base_retry_seconds=settings.NOTIFICATION_WORKER_BASE_RETRY_SECONDS,
            max_retry_seconds=settings.NOTIFICATION_WORKER_MAX_RETRY_SECONDS,
            jitter_seconds=settings.NOTIFICATION_WORKER_JITTER_SECONDS,
        )
        for delivery in plan_result.deliveries:
            if delivery.channel != "whatsapp" or delivery.status != "pending":
                continue
            scheduled_for = self._ensure_utc_aware(delivery.scheduled_for)
            if scheduled_for > now:
                continue
            try:
                result = executor.execute(tenant_id=tenant_id, delivery_id=delivery.id, now=now)
            except Exception as exc:  # noqa: BLE001 - one failed delivery must not block the rest
                self.db.rollback()
                self._log_safe_error(tenant_id=tenant_id, resource_id=delivery.id, exc=exc)
                continue
            if result.outcome == "failed":
                try:
                    retry_policy.apply_failure(
                        tenant_id=tenant_id,
                        delivery_id=delivery.id,
                        now=now,
                        error_code=result.error_code or "whatsapp_provider_send_failed",
                        retryable=result.retryable if result.retryable is not None else True,
                        max_attempts=settings.NOTIFICATION_WORKER_MAX_ATTEMPTS,
                    )
                except Exception as exc:  # noqa: BLE001 - retry scheduling must not break the caller
                    self.db.rollback()
                    self._log_safe_error(tenant_id=tenant_id, resource_id=delivery.id, exc=exc)

        sent_count = sum(1 for d in plan_result.deliveries if d.status in ("sent", "delivered", "read"))
        failed_count = sum(1 for d in plan_result.deliveries if d.status == "failed")
        pending_count = sum(1 for d in plan_result.deliveries if d.status == "pending")
        skipped_count = sum(1 for d in plan_result.deliveries if d.status in ("skipped", "cancelled"))

        status = "partial" if failed_count > 0 else "processed"

        return NotificationEventPipelineResult(
            status=status,
            event_id=event.id,
            event_created=event_created,
            planned_delivery_count=len(plan_result.deliveries),
            sent_count=sent_count,
            failed_count=failed_count,
            pending_count=pending_count,
            skipped_count=skipped_count,
        )

    @staticmethod
    def _same_identity(
        event: DomainEvent, *, event_type: str, resource_type: str, resource_id: str
    ) -> bool:
        return (
            event.event_type == event_type
            and event.resource_type == resource_type
            and event.resource_id == resource_id
        )

    # ------------------------------------------------------------------
    # Payload builders
    # ------------------------------------------------------------------
    def _booking_payload(self, *, tenant_id: str, booking: CrmBooking) -> dict[str, Any]:
        booking_dict: dict[str, Any] = {
            "id": booking.id,
            "status": booking.status,
            "title": booking.title,
            "start_at": self._iso(booking.start_at),
            "timezone": booking.timezone,
            "meeting_url": booking.meeting_url,
        }
        if booking.end_at is not None:
            booking_dict["end_at"] = self._iso(booking.end_at)

        payload: dict[str, Any] = {"booking": booking_dict}

        customer = {
            "name": booking.attendee_name or None,
            "phone": booking.attendee_phone or None,
            "email": booking.attendee_email or None,
        }
        if any(customer.values()):
            payload["customer"] = customer

        if booking.lead_id:
            lead = self.db.scalar(
                select(CrmLead).where(CrmLead.tenant_id == tenant_id, CrmLead.id == booking.lead_id)
            )
            if lead is not None:
                payload["lead"] = {"id": lead.id, "status": lead.status}

        payload["custom"] = self._safe_custom(booking.metadata_json)
        return payload

    def _call_payload(self, *, tenant_id: str, call: CrmVoiceCall) -> dict[str, Any]:
        summary = call.summary[:4000] if isinstance(call.summary, str) else call.summary
        call_dict: dict[str, Any] = {
            "id": call.id,
            "provider": call.provider,
            "provider_call_id": call.provider_call_id,
            "status": call.status,
            "duration_seconds": call.duration_seconds,
            "summary": summary,
            "outcome": call.status,
        }
        payload: dict[str, Any] = {"call": call_dict}

        if call.contact_id:
            contact = self.db.scalar(
                select(CrmContact).where(CrmContact.tenant_id == tenant_id, CrmContact.id == call.contact_id)
            )
            if contact is not None:
                customer = {
                    "name": contact.name or None,
                    "phone": contact.phone or None,
                    "email": contact.email or None,
                }
                if any(customer.values()):
                    payload["customer"] = customer

        if call.lead_id:
            lead = self.db.scalar(
                select(CrmLead).where(CrmLead.tenant_id == tenant_id, CrmLead.id == call.lead_id)
            )
            if lead is not None:
                payload["lead"] = {"id": lead.id, "status": lead.status}

        payload["custom"] = {}
        return payload

    # ------------------------------------------------------------------
    # Idempotency keys
    # ------------------------------------------------------------------
    def _booking_idempotency_key(self, *, booking: CrmBooking, event_type: str) -> str:
        if event_type == "booking.created":
            return f"booking:{booking.id}:created"
        if event_type == "booking.cancelled":
            return f"booking:{booking.id}:cancelled"

        start_norm = self._iso(booking.start_at)
        end_norm = self._iso(booking.end_at) if booking.end_at is not None else ""
        digest = hashlib.sha256(f"{booking.id}:{start_norm}:{end_norm}".encode("utf-8")).hexdigest()[:24]
        return f"booking:{booking.id}:rescheduled:{digest}"

    @staticmethod
    def _call_idempotency_key(*, call: CrmVoiceCall, event_type: str) -> str:
        suffix = _CALL_IDEMPOTENCY_SUFFIX[event_type]
        return f"voice_call:{call.id}:{suffix}"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _safe_custom(metadata_json: Any) -> dict[str, Any]:
        if not isinstance(metadata_json, dict):
            return {}
        custom = metadata_json.get("notification_custom")
        if not isinstance(custom, dict):
            return {}
        try:
            _check_json_safe(custom, depth=1)
        except ValueError:
            return {}
        return custom

    @staticmethod
    def _iso(value: datetime) -> str:
        aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return aware.astimezone(timezone.utc).isoformat()

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

    @staticmethod
    def _log_safe_error(*, tenant_id: str, resource_id: str, exc: Exception) -> None:
        logger.error(
            "notification_event_pipeline_error tenant_id=%s resource_id=%s error_type=%s",
            tenant_id,
            resource_id,
            type(exc).__name__,
        )


# --------------------------------------------------------------------------
# BackgroundTasks adapters (ephemeral — replaced by a durable worker in Phase 6)
# --------------------------------------------------------------------------
def run_booking_notification_pipeline_task(*, tenant_id: str, booking_id: str, event_type: str) -> None:
    db = SessionLocal()
    try:
        NotificationEventPipeline(db).process_booking_event(
            tenant_id=tenant_id, booking_id=booking_id, event_type=event_type
        )
    except Exception as exc:  # noqa: BLE001 - background task must never raise
        logger.error(
            "notification_event_pipeline_task_error tenant_id=%s resource_id=%s error_type=%s",
            tenant_id,
            booking_id,
            type(exc).__name__,
        )
    finally:
        db.close()


def run_call_notification_pipeline_task(*, tenant_id: str, voice_call_id: str) -> None:
    db = SessionLocal()
    try:
        NotificationEventPipeline(db).process_call_event(tenant_id=tenant_id, voice_call_id=voice_call_id)
    except Exception as exc:  # noqa: BLE001 - background task must never raise
        logger.error(
            "notification_event_pipeline_task_error tenant_id=%s resource_id=%s error_type=%s",
            tenant_id,
            voice_call_id,
            type(exc).__name__,
        )
    finally:
        db.close()
