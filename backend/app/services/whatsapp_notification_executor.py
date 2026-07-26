from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.notification_variables import (
    NotificationVariableConfigurationError,
    NotificationVariableMappingError,
)
from app.models.crm import CrmLead, CrmWhatsAppMessage
from app.models.notifications import DomainEvent, NotificationDelivery, TenantNotificationRule
from app.services.notification_variable_mapper import NotificationVariableMapper
from app.services.whatsapp_client import WhatsAppCloudClient
from app.services.whatsapp_message_service import WhatsAppMessageService
from app.services.whatsapp_template_service import WhatsAppTemplateService

_TERMINAL_COMPLETED_STATUSES = {"sent", "delivered", "read"}
_EXECUTABLE_STATUSES = {"pending", "failed"}


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


class WhatsAppNotificationExecutor:
    def __init__(self, db: Session, client: WhatsAppCloudClient | None = None) -> None:
        self.db = db
        self._message_service = WhatsAppMessageService(db, client=client)
        self._templates = WhatsAppTemplateService(db)
        self._variable_mapper = NotificationVariableMapper()

    def execute(
        self,
        *,
        tenant_id: str,
        delivery_id: str,
        now: datetime | None = None,
    ) -> WhatsAppNotificationExecutionResult:
        current_time = self._resolve_now(now)

        delivery = self._load_delivery(tenant_id=tenant_id, delivery_id=delivery_id)
        event, rule = self._load_related(tenant_id=tenant_id, delivery=delivery)

        if delivery.status in _TERMINAL_COMPLETED_STATUSES:
            return WhatsAppNotificationExecutionResult(delivery=delivery, message=None, outcome="already_completed")
        if delivery.status == "skipped":
            return WhatsAppNotificationExecutionResult(delivery=delivery, message=None, outcome="skipped")
        if delivery.status == "cancelled":
            return WhatsAppNotificationExecutionResult(delivery=delivery, message=None, outcome="cancelled")
        if delivery.status == "processing":
            raise WhatsAppNotificationExecutionError(
                tenant_id=tenant_id, delivery_id=delivery_id, code="delivery_already_processing"
            )
        if delivery.status not in _EXECUTABLE_STATUSES:
            raise WhatsAppNotificationExecutionError(
                tenant_id=tenant_id, delivery_id=delivery_id, code="delivery_status_unsupported"
            )

        scheduled_for = self._ensure_utc_aware(delivery.scheduled_for)
        if scheduled_for > current_time:
            return WhatsAppNotificationExecutionResult(delivery=delivery, message=None, outcome="not_due")

        delivery.status = "processing"
        delivery.attempts += 1
        delivery.error_message = None
        self.db.add(delivery)
        self.db.commit()
        self.db.refresh(delivery)

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
            self._fail_before_send(tenant_id=tenant_id, delivery_id=delivery_id, code=exc.code)
        except NotificationVariableMappingError as exc:
            self._fail_before_send(tenant_id=tenant_id, delivery_id=delivery_id, code=exc.code)
        except ValueError:
            self._fail_before_send(
                tenant_id=tenant_id, delivery_id=delivery_id, code="template_configuration_invalid"
            )

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
                lead_id=lead_id,
                contact_id=contact_id,
            )
        except ValueError:
            self._fail_before_send(
                tenant_id=tenant_id, delivery_id=delivery_id, code="whatsapp_send_precondition_failed"
            )

        delivery = self._load_delivery(tenant_id=tenant_id, delivery_id=delivery_id)
        metadata_json = dict(delivery.metadata_json or {})
        if result.message is not None:
            metadata_json["crm_whatsapp_message_id"] = result.message.id
        delivery.metadata_json = metadata_json

        if result.status == "sent":
            delivery.status = "sent"
            delivery.provider_message_id = result.provider_message_id
            delivery.sent_at = current_time
            delivery.error_message = None
            self.db.add(delivery)
            self.db.commit()
            self.db.refresh(delivery)
            return WhatsAppNotificationExecutionResult(delivery=delivery, message=result.message, outcome="sent")

        delivery.status = "failed"
        delivery.failed_at = current_time
        delivery.error_message = result.error_message
        self.db.add(delivery)
        self.db.commit()
        self.db.refresh(delivery)
        return WhatsAppNotificationExecutionResult(delivery=delivery, message=result.message, outcome="failed")

    def _fail_before_send(self, *, tenant_id: str, delivery_id: str, code: str) -> None:
        self.db.rollback()
        delivery = self._load_delivery(tenant_id=tenant_id, delivery_id=delivery_id)
        delivery.status = "failed"
        delivery.failed_at = datetime.now(timezone.utc)
        delivery.error_message = code
        self.db.add(delivery)
        self.db.commit()
        raise WhatsAppNotificationExecutionError(tenant_id=tenant_id, delivery_id=delivery_id, code=code)

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
