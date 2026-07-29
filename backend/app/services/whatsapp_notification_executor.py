from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.notification_delivery_state import CLAIMABLE_STATUSES, FINAL_NON_RETRYABLE_STATUSES
from app.domain.notification_variables import (
    NotificationVariableConfigurationError,
    NotificationVariableMappingError,
)
from app.models.crm import CrmLead, CrmWhatsAppMessage
from app.models.notifications import DomainEvent, NotificationDelivery, TenantNotificationRule
from app.services.notification_delivery_claim_service import NotificationDeliveryClaimService
from app.services.notification_variable_mapper import NotificationVariableMapper
from app.services.whatsapp_client import WhatsAppCloudClient
from app.services.whatsapp_message_service import WhatsAppMessageService
from app.services.whatsapp_template_service import WhatsAppTemplateService

_RESCHEDULE_SUPERSEDABLE_TYPES = {"booking.created", "booking.rescheduled"}
_RESCHEDULE_EVENT_TYPES = {"booking.cancelled", "booking.rescheduled"}
_STALE_CLAIM_RANK = {"sent": 1, "delivered": 2, "read": 3}


class WhatsAppNotificationExecutionError(RuntimeError):
    def __init__(self, *, tenant_id: str, delivery_id: str, code: str) -> None:
        super().__init__(
            f"WhatsApp notification execution error tenant_id={tenant_id} delivery_id={delivery_id} code={code}"
        )
        self.tenant_id = tenant_id
        self.delivery_id = delivery_id
        self.code = code


@dataclass(frozen=True)
class WhatsAppNotificationExecutionResult:
    delivery: NotificationDelivery
    message: CrmWhatsAppMessage | None
    outcome: str
    error_code: str | None = None
    retryable: bool | None = None


class WhatsAppNotificationExecutor:
    def __init__(
        self,
        db: Session,
        client: WhatsAppCloudClient | None = None,
        *,
        lease_seconds: int | None = None,
        max_attempts: int | None = None,
    ) -> None:
        self.db = db
        self._message_service = WhatsAppMessageService(db, client=client)
        self._templates = WhatsAppTemplateService(db)
        self._variable_mapper = NotificationVariableMapper()
        self._claims = NotificationDeliveryClaimService(db)
        self._lease_seconds = (
            lease_seconds if lease_seconds is not None else settings.NOTIFICATION_WORKER_LEASE_SECONDS
        )
        self._max_attempts = (
            max_attempts if max_attempts is not None else settings.NOTIFICATION_WORKER_MAX_ATTEMPTS
        )

    # ------------------------------------------------------------------
    # Direct execution (Phase 5 compatibility) — claims atomically, then
    # delegates to execute_claimed.
    # ------------------------------------------------------------------
    def execute(
        self,
        *,
        tenant_id: str,
        delivery_id: str,
        now: datetime | None = None,
    ) -> WhatsAppNotificationExecutionResult:
        current_time = self._resolve_now(now)
        delivery = self._load_delivery(tenant_id=tenant_id, delivery_id=delivery_id)

        if delivery.status in FINAL_NON_RETRYABLE_STATUSES:
            if delivery.status == "skipped":
                return WhatsAppNotificationExecutionResult(delivery=delivery, message=None, outcome="skipped")
            if delivery.status == "cancelled":
                return WhatsAppNotificationExecutionResult(delivery=delivery, message=None, outcome="cancelled")
            return WhatsAppNotificationExecutionResult(delivery=delivery, message=None, outcome="already_completed")
        if delivery.status == "processing":
            raise WhatsAppNotificationExecutionError(
                tenant_id=tenant_id, delivery_id=delivery_id, code="delivery_already_processing"
            )
        if delivery.status not in CLAIMABLE_STATUSES:
            raise WhatsAppNotificationExecutionError(
                tenant_id=tenant_id, delivery_id=delivery_id, code="delivery_status_unsupported"
            )

        scheduled_for = self._ensure_utc_aware(delivery.scheduled_for)
        if scheduled_for > current_time:
            return WhatsAppNotificationExecutionResult(delivery=delivery, message=None, outcome="not_due")

        claim = self._claims.claim_one(
            tenant_id=tenant_id,
            delivery_id=delivery_id,
            now=current_time,
            lease_seconds=self._lease_seconds,
            max_attempts=self._max_attempts,
        )
        if claim is None:
            raise WhatsAppNotificationExecutionError(
                tenant_id=tenant_id, delivery_id=delivery_id, code="delivery_claim_unavailable"
            )

        return self.execute_claimed(
            tenant_id=tenant_id,
            delivery_id=delivery_id,
            claim_token=claim.claim_token,
            now=current_time,
        )

    # ------------------------------------------------------------------
    # Claimed execution — the durable worker calls this directly with a
    # claim token it already owns.
    # ------------------------------------------------------------------
    def execute_claimed(
        self,
        *,
        tenant_id: str,
        delivery_id: str,
        claim_token: str,
        now: datetime | None = None,
    ) -> WhatsAppNotificationExecutionResult:
        current_time = self._resolve_now(now)

        # An empty or mismatched token never mutates the delivery: it may be
        # actively owned by another process, so we must not disturb it.
        delivery = self._load_delivery(tenant_id=tenant_id, delivery_id=delivery_id)
        self._assert_claim_owner(tenant_id=tenant_id, delivery=delivery, claim_token=claim_token)

        try:
            event, rule = self._load_related(tenant_id=tenant_id, delivery=delivery)
        except WhatsAppNotificationExecutionError as exc:
            self._fail_claimed(tenant_id=tenant_id, delivery_id=delivery_id, now=current_time, code=exc.code)

        cancelled = self._check_cancellation(tenant_id=tenant_id, delivery=delivery, event=event)
        if cancelled is not None:
            return cancelled

        try:
            variables = self._variable_mapper.map_variables(
                tenant_id=tenant_id,
                rule_id=rule.id,
                mapping=rule.variable_mapping_json,
                payload=event.payload_json,
            )
            template = self._templates.get_synced_template(
                tenant_id,
                template_key=delivery.template_key or rule.template_key,
                provider_template_name=None,
            )
            required_keys = self._templates.get_approved_parameter_keys(template)
            missing = [key for key in required_keys if key not in variables]
            if missing:
                raise NotificationVariableMappingError(
                    tenant_id=tenant_id, rule_id=rule.id, code="template_variable_missing"
                )
            lead_id, contact_id = self._resolve_crm_link(tenant_id=tenant_id, event=event)
        except NotificationVariableConfigurationError as exc:
            self._fail_claimed(tenant_id=tenant_id, delivery_id=delivery_id, now=current_time, code=exc.code)
        except NotificationVariableMappingError as exc:
            self._fail_claimed(tenant_id=tenant_id, delivery_id=delivery_id, now=current_time, code=exc.code)
        except ValueError:
            self._fail_claimed(
                tenant_id=tenant_id, delivery_id=delivery_id, now=current_time, code="template_configuration_invalid"
            )

        # Refresh immediately before calling Meta and re-check everything.
        delivery = self._load_delivery(tenant_id=tenant_id, delivery_id=delivery_id)
        self._assert_claim_owner(tenant_id=tenant_id, delivery=delivery, claim_token=claim_token)
        cancelled = self._check_cancellation(tenant_id=tenant_id, delivery=delivery, event=event)
        if cancelled is not None:
            return cancelled

        metadata = {
            "source": "notification_delivery",
            "notification_delivery_id": delivery.id,
            "domain_event_id": event.id,
            "notification_rule_id": rule.id,
            "template_key": template.template_key,
        }

        try:
            result = self._message_service.send_template_notification(
                tenant_id=tenant_id,
                to_phone=delivery.recipient,
                template_key=template.template_key,
                variables=variables,
                metadata=metadata,
                notification_delivery_id=delivery.id,
                lead_id=lead_id,
                contact_id=contact_id,
            )
        except ValueError:
            self._fail_claimed(
                tenant_id=tenant_id,
                delivery_id=delivery_id,
                now=current_time,
                code="whatsapp_send_precondition_failed",
            )

        if result.status == "manual_review":
            # send_template_notification already parked the delivery in
            # manual_review itself (Meta answered but gave no usable message
            # id) — just report what happened, no further mutation here.
            delivery = self._load_delivery(tenant_id=tenant_id, delivery_id=delivery_id)
            return WhatsAppNotificationExecutionResult(
                delivery=delivery,
                message=result.message,
                outcome="manual_review",
                error_code="whatsapp_provider_message_id_missing",
                retryable=False,
            )

        return self._finalize_after_send(
            tenant_id=tenant_id,
            delivery_id=delivery_id,
            claim_token=claim_token,
            current_time=current_time,
            result=result,
        )

    # ------------------------------------------------------------------
    # Post-Meta finalization — the HTTP call may have taken long enough for
    # the lease to expire and a different execution to take over, so the
    # outcome is only written back if this call still owns the claim.
    # ------------------------------------------------------------------
    def _finalize_after_send(
        self,
        *,
        tenant_id: str,
        delivery_id: str,
        claim_token: str,
        current_time: datetime,
        result,
    ) -> WhatsAppNotificationExecutionResult:
        delivery = self._load_delivery(tenant_id=tenant_id, delivery_id=delivery_id)
        owns_claim = delivery.status == "processing" and delivery.claim_token == claim_token

        if not owns_claim:
            return self._reconcile_stale_claim(tenant_id=tenant_id, delivery_id=delivery_id, result=result)

        metadata_json = dict(delivery.metadata_json or {})
        if result.message is not None:
            metadata_json["crm_whatsapp_message_id"] = result.message.id
        delivery.metadata_json = metadata_json

        if result.status == "sent":
            delivery.status = "sent"
            delivery.provider_message_id = result.provider_message_id
            delivery.sent_at = current_time
            delivery.error_message = None
            delivery.next_attempt_at = None
            delivery.claim_token = None
            delivery.claimed_at = None
            delivery.claim_expires_at = None
            self.db.add(delivery)
            self.db.commit()
            self.db.refresh(delivery)
            return WhatsAppNotificationExecutionResult(delivery=delivery, message=result.message, outcome="sent")

        delivery.status = "failed"
        delivery.failed_at = current_time
        delivery.error_message = "whatsapp_provider_send_failed"
        delivery.claim_token = None
        delivery.claimed_at = None
        delivery.claim_expires_at = None
        self.db.add(delivery)
        self.db.commit()
        self.db.refresh(delivery)
        return WhatsAppNotificationExecutionResult(
            delivery=delivery,
            message=result.message,
            outcome="failed",
            error_code="whatsapp_provider_send_failed",
            retryable=True,
        )

    def _reconcile_stale_claim(
        self, *, tenant_id: str, delivery_id: str, result
    ) -> WhatsAppNotificationExecutionResult:
        delivery = self._load_delivery(tenant_id=tenant_id, delivery_id=delivery_id)

        if delivery.status in FINAL_NON_RETRYABLE_STATUSES:
            return WhatsAppNotificationExecutionResult(
                delivery=delivery, message=result.message, outcome="stale_claim_ignored"
            )

        message = self.db.scalar(
            select(CrmWhatsAppMessage)
            .where(
                CrmWhatsAppMessage.tenant_id == tenant_id,
                CrmWhatsAppMessage.notification_delivery_id == delivery_id,
            )
            .order_by(CrmWhatsAppMessage.created_at.desc(), CrmWhatsAppMessage.id.desc())
        )
        if message is None or not message.provider_message_id or message.status not in _STALE_CLAIM_RANK:
            return WhatsAppNotificationExecutionResult(
                delivery=delivery, message=result.message, outcome="stale_claim_ignored"
            )

        current_rank = _STALE_CLAIM_RANK.get(delivery.status, 0)
        new_rank = _STALE_CLAIM_RANK[message.status]
        if new_rank < current_rank:
            return WhatsAppNotificationExecutionResult(
                delivery=delivery, message=result.message, outcome="stale_claim_ignored"
            )

        delivery.status = message.status
        delivery.provider_message_id = message.provider_message_id
        if message.status in ("sent", "delivered", "read"):
            delivery.sent_at = delivery.sent_at or message.sent_at
        if message.status in ("delivered", "read"):
            delivery.delivered_at = delivery.delivered_at or message.delivered_at
        if message.status == "read":
            delivery.read_at = delivery.read_at or message.read_at
        delivery.next_attempt_at = None
        delivery.error_message = None
        self.db.add(delivery)
        self.db.commit()
        self.db.refresh(delivery)
        return WhatsAppNotificationExecutionResult(
            delivery=delivery, message=message, outcome="stale_claim_reconciled"
        )

    # ------------------------------------------------------------------
    # Cancellation checks
    # ------------------------------------------------------------------
    def _check_cancellation(
        self, *, tenant_id: str, delivery: NotificationDelivery, event: DomainEvent
    ) -> WhatsAppNotificationExecutionResult | None:
        metadata = delivery.metadata_json or {}
        if metadata.get("cancel_requested"):
            reason = metadata.get("cancel_reason") or "booking_cancelled"
            return self._cancel(tenant_id=tenant_id, delivery_id=delivery.id, reason=reason)

        if event.resource_type == "crm_booking" and event.resource_id and event.event_type in _RESCHEDULE_SUPERSEDABLE_TYPES:
            superseding = self._find_superseding_event(tenant_id=tenant_id, event=event)
            if superseding is not None:
                reason = (
                    "booking_cancelled"
                    if superseding.event_type == "booking.cancelled"
                    else "booking_schedule_superseded"
                )
                return self._cancel(tenant_id=tenant_id, delivery_id=delivery.id, reason=reason)
        return None

    def _find_superseding_event(self, *, tenant_id: str, event: DomainEvent) -> DomainEvent | None:
        candidates = self.db.scalars(
            select(DomainEvent).where(
                DomainEvent.tenant_id == tenant_id,
                DomainEvent.resource_type == "crm_booking",
                DomainEvent.resource_id == event.resource_id,
                DomainEvent.event_type.in_(_RESCHEDULE_EVENT_TYPES),
            )
        ).all()
        newest: DomainEvent | None = None
        for candidate in candidates:
            if candidate.id == event.id:
                continue
            if not self._is_after(candidate, event):
                continue
            if newest is None or self._is_after(candidate, newest):
                newest = candidate
        return newest

    @staticmethod
    def _is_after(a: DomainEvent, b: DomainEvent) -> bool:
        if a.created_at != b.created_at:
            return a.created_at > b.created_at
        return a.id > b.id

    def _cancel(self, *, tenant_id: str, delivery_id: str, reason: str) -> WhatsAppNotificationExecutionResult:
        delivery = self._load_delivery(tenant_id=tenant_id, delivery_id=delivery_id)
        delivery.status = "cancelled"
        delivery.next_attempt_at = None
        delivery.error_message = reason
        delivery.claim_token = None
        delivery.claimed_at = None
        delivery.claim_expires_at = None
        self.db.add(delivery)
        self.db.commit()
        self.db.refresh(delivery)
        return WhatsAppNotificationExecutionResult(delivery=delivery, message=None, outcome="cancelled")

    # ------------------------------------------------------------------
    # Failure helper — always raises after leaving the delivery in a safe,
    # unclaimed `failed` state.
    # ------------------------------------------------------------------
    def _fail_claimed(self, *, tenant_id: str, delivery_id: str, now: datetime, code: str) -> None:
        self.db.rollback()
        delivery = self._load_delivery(tenant_id=tenant_id, delivery_id=delivery_id)
        delivery.status = "failed"
        delivery.failed_at = now
        delivery.error_message = code
        # No provider call was made for these pre-send failures, so there is
        # no ambiguous in-flight send to protect against — release the claim
        # immediately instead of waiting out the lease window.
        delivery.next_attempt_at = None
        delivery.claim_token = None
        delivery.claimed_at = None
        delivery.claim_expires_at = None
        self.db.add(delivery)
        self.db.commit()
        raise WhatsAppNotificationExecutionError(tenant_id=tenant_id, delivery_id=delivery_id, code=code)

    def _assert_claim_owner(
        self, *, tenant_id: str, delivery: NotificationDelivery, claim_token: str
    ) -> None:
        if delivery.status != "processing" or not delivery.claim_token or delivery.claim_token != claim_token:
            raise WhatsAppNotificationExecutionError(
                tenant_id=tenant_id, delivery_id=delivery.id, code="delivery_claim_mismatch"
            )

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------
    def _load_delivery(self, *, tenant_id: str, delivery_id: str) -> NotificationDelivery:
        delivery = self.db.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.tenant_id == tenant_id,
                NotificationDelivery.id == delivery_id,
            )
        )
        if delivery is None:
            raise WhatsAppNotificationExecutionError(
                tenant_id=tenant_id, delivery_id=delivery_id, code="delivery_not_found"
            )
        return delivery

    def _load_related(
        self, *, tenant_id: str, delivery: NotificationDelivery
    ) -> tuple[DomainEvent, TenantNotificationRule]:
        event = self.db.scalar(
            select(DomainEvent).where(
                DomainEvent.tenant_id == tenant_id,
                DomainEvent.id == delivery.domain_event_id,
            )
        )
        rule = self.db.scalar(
            select(TenantNotificationRule).where(
                TenantNotificationRule.tenant_id == tenant_id,
                TenantNotificationRule.id == delivery.notification_rule_id,
            )
        )
        if event is None or rule is None:
            raise WhatsAppNotificationExecutionError(
                tenant_id=tenant_id, delivery_id=delivery.id, code="delivery_related_records_missing"
            )
        if delivery.tenant_id != tenant_id or event.tenant_id != tenant_id or rule.tenant_id != tenant_id:
            raise WhatsAppNotificationExecutionError(
                tenant_id=tenant_id, delivery_id=delivery.id, code="tenant_mismatch"
            )
        if delivery.channel != "whatsapp" or rule.action_type != "send_whatsapp_template":
            raise WhatsAppNotificationExecutionError(
                tenant_id=tenant_id, delivery_id=delivery.id, code="unsupported_delivery_action"
            )
        return event, rule

    def _resolve_crm_link(self, *, tenant_id: str, event: DomainEvent) -> tuple[str | None, str | None]:
        payload = event.payload_json if isinstance(event.payload_json, dict) else {}
        lead_ref = payload.get("lead")
        lead_id = lead_ref.get("id") if isinstance(lead_ref, dict) else None
        if not lead_id:
            return None, None
        lead = self.db.scalar(select(CrmLead).where(CrmLead.tenant_id == tenant_id, CrmLead.id == lead_id))
        if lead is None:
            return None, None
        return lead.id, lead.contact_id

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
