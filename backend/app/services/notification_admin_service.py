from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.events import SUPPORTED_DOMAIN_EVENT_TYPES
from app.domain.notification_delivery_state import (
    CANCELLED,
    DEAD_LETTER,
    DELIVERED,
    FAILED,
    MANUAL_REVIEW,
    PENDING,
    PROCESSING,
    READ,
    SENT,
)
from app.domain.notification_rules import (
    NotificationConditionOperator,
    NotificationRuleConfigurationError,
    SUPPORTED_NOTIFICATION_ACTIONS,
    SUPPORTED_NOTIFICATION_CHANNELS,
    SUPPORTED_RECIPIENT_STRATEGIES,
    SUPPORTED_SCHEDULE_MODES,
    validate_notification_rule,
)
from app.domain.notification_variables import (
    NotificationVariableConfigurationError,
    NotificationVariableFormat,
    NotificationVariableSource,
    validate_variable_mapping,
)
from app.models.notifications import (
    DomainEvent,
    NotificationDelivery,
    TenantCapability,
    TenantNotificationRecipient,
    TenantNotificationRule,
)
from app.services.whatsapp_message_service import mask_phone, normalize_phone

KNOWN_CAPABILITY_KEYS = ("booking_notifications", "call_notifications")
_RECIPIENT_STATUSES = {"active", "inactive"}
_MIN_DESTINATION_LENGTH = 8
_MAX_DESTINATION_LENGTH = 32
_DEFAULT_PAGE_SIZE = 25
_MAX_PAGE_SIZE = 100
_FIXED_CHANNEL = "whatsapp"
_FIXED_ACTION_TYPE = "send_whatsapp_template"


class NotificationAdminError(ValueError):
    def __init__(self, *, code: str, kind: str = "unprocessable") -> None:
        super().__init__(f"Notification admin error code={code} kind={kind}")
        self.code = code
        self.kind = kind


class NotificationAdminService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------------------------------------------------------------- overview
    def get_overview(self, *, tenant_id: str) -> dict[str, Any]:
        capability_rows = self.db.execute(
            select(TenantCapability.enabled, func.count())
            .where(TenantCapability.tenant_id == tenant_id)
            .group_by(TenantCapability.enabled)
        ).all()
        rule_rows = self.db.execute(
            select(TenantNotificationRule.enabled, func.count())
            .where(TenantNotificationRule.tenant_id == tenant_id)
            .group_by(TenantNotificationRule.enabled)
        ).all()
        recipient_rows = self.db.execute(
            select(TenantNotificationRecipient.status, func.count())
            .where(TenantNotificationRecipient.tenant_id == tenant_id)
            .group_by(TenantNotificationRecipient.status)
        ).all()
        delivery_rows = self.db.execute(
            select(NotificationDelivery.status, func.count())
            .where(NotificationDelivery.tenant_id == tenant_id)
            .group_by(NotificationDelivery.status)
        ).all()
        delivery_counts = {status: count for status, count in delivery_rows}

        return {
            "capabilities": {
                "total": sum(count for _, count in capability_rows),
                "enabled": sum(count for enabled, count in capability_rows if enabled),
            },
            "rules": {
                "total": sum(count for _, count in rule_rows),
                "enabled": sum(count for enabled, count in rule_rows if enabled),
            },
            "recipients": {
                "total": sum(count for _, count in recipient_rows),
                "active": sum(count for status, count in recipient_rows if status == "active"),
            },
            "deliveries": {
                "pending": delivery_counts.get(PENDING, 0),
                "processing": delivery_counts.get(PROCESSING, 0),
                "sent": delivery_counts.get(SENT, 0),
                "delivered": delivery_counts.get(DELIVERED, 0),
                "read": delivery_counts.get(READ, 0),
                "failed": delivery_counts.get(FAILED, 0),
                "dead_letter": delivery_counts.get(DEAD_LETTER, 0),
                "manual_review": delivery_counts.get(MANUAL_REVIEW, 0),
                "cancelled": delivery_counts.get(CANCELLED, 0),
            },
        }

    # ----------------------------------------------------------------- catalog
    def get_catalog(self) -> dict[str, Any]:
        return {
            "event_types": sorted(SUPPORTED_DOMAIN_EVENT_TYPES),
            "capability_keys": list(KNOWN_CAPABILITY_KEYS),
            "channels": sorted(SUPPORTED_NOTIFICATION_CHANNELS),
            "action_types": sorted(SUPPORTED_NOTIFICATION_ACTIONS),
            "recipient_strategies": sorted(SUPPORTED_RECIPIENT_STRATEGIES),
            "schedule_modes": sorted(SUPPORTED_SCHEDULE_MODES),
            "condition_operators": [operator.value for operator in NotificationConditionOperator],
            "variable_sources": [source.value for source in NotificationVariableSource],
            "variable_formats": [fmt.value for fmt in NotificationVariableFormat],
        }

    # ------------------------------------------------------------- capabilities
    def list_capabilities(self, *, tenant_id: str) -> list[TenantCapability]:
        existing = {
            row.capability_key: row
            for row in self.db.query(TenantCapability)
            .filter(TenantCapability.tenant_id == tenant_id)
            .all()
        }
        result: list[TenantCapability] = []
        for key in KNOWN_CAPABILITY_KEYS:
            if key in existing:
                result.append(existing[key])
            else:
                result.append(TenantCapability(tenant_id=tenant_id, capability_key=key, enabled=False, config_json={}))
        return result

    def update_capability(
        self, *, tenant_id: str, capability_key: str, enabled: bool, config_json: Optional[dict]
    ) -> TenantCapability:
        if capability_key not in KNOWN_CAPABILITY_KEYS:
            raise NotificationAdminError(code="unknown_capability_key", kind="unprocessable")

        capability = (
            self.db.query(TenantCapability)
            .filter(
                TenantCapability.tenant_id == tenant_id,
                TenantCapability.capability_key == capability_key,
            )
            .first()
        )
        if capability is None:
            capability = TenantCapability(tenant_id=tenant_id, capability_key=capability_key, config_json={})
            self.db.add(capability)
        capability.enabled = enabled
        if config_json is not None:
            capability.config_json = config_json
        self.db.commit()
        self.db.refresh(capability)
        return capability

    # -------------------------------------------------------------------- rules
    def list_rules(self, *, tenant_id: str) -> list[TenantNotificationRule]:
        return (
            self.db.query(TenantNotificationRule)
            .filter(TenantNotificationRule.tenant_id == tenant_id)
            .order_by(TenantNotificationRule.priority.asc(), TenantNotificationRule.created_at.asc())
            .all()
        )

    def get_rule(self, *, tenant_id: str, rule_id: str) -> Optional[TenantNotificationRule]:
        return (
            self.db.query(TenantNotificationRule)
            .filter(TenantNotificationRule.tenant_id == tenant_id, TenantNotificationRule.id == rule_id)
            .first()
        )

    def rule_configuration_error(self, rule: TenantNotificationRule) -> Optional[str]:
        try:
            validate_notification_rule(rule)
            validate_variable_mapping(rule.variable_mapping_json)
        except NotificationRuleConfigurationError as exc:
            return exc.code
        except NotificationVariableConfigurationError as exc:
            return exc.code
        return None

    def create_rule(self, *, tenant_id: str, payload) -> TenantNotificationRule:
        if payload.event_type not in SUPPORTED_DOMAIN_EVENT_TYPES:
            raise NotificationAdminError(code="unsupported_event_type", kind="unprocessable")
        if payload.capability_key not in KNOWN_CAPABILITY_KEYS:
            raise NotificationAdminError(code="unsupported_capability_key", kind="unprocessable")

        duplicate = (
            self.db.query(TenantNotificationRule)
            .filter(TenantNotificationRule.tenant_id == tenant_id, TenantNotificationRule.name == payload.name)
            .first()
        )
        if duplicate is not None:
            raise NotificationAdminError(code="duplicate_name", kind="conflict")

        rule = TenantNotificationRule(
            tenant_id=tenant_id,
            name=payload.name,
            capability_key=payload.capability_key,
            event_type=payload.event_type,
            channel=_FIXED_CHANNEL,
            action_type=_FIXED_ACTION_TYPE,
            template_key=payload.template_key,
            recipient_strategy=payload.recipient_strategy,
            recipient_group_key=payload.recipient_group_key,
            conditions_json=payload.conditions_json,
            variable_mapping_json=payload.variable_mapping_json,
            schedule_mode=payload.schedule_mode,
            schedule_offset_minutes=payload.schedule_offset_minutes,
            priority=payload.priority,
            enabled=payload.enabled,
        )
        self._validate_rule_or_raise(rule)

        self.db.add(rule)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise NotificationAdminError(code="duplicate_name", kind="conflict") from None
        self.db.refresh(rule)
        return rule

    def update_rule(self, *, tenant_id: str, rule_id: str, payload) -> Optional[TenantNotificationRule]:
        rule = self.get_rule(tenant_id=tenant_id, rule_id=rule_id)
        if rule is None:
            return None

        updates = payload.model_dump(exclude_unset=True)

        if "event_type" in updates and updates["event_type"] not in SUPPORTED_DOMAIN_EVENT_TYPES:
            raise NotificationAdminError(code="unsupported_event_type", kind="unprocessable")
        if "capability_key" in updates and updates["capability_key"] not in KNOWN_CAPABILITY_KEYS:
            raise NotificationAdminError(code="unsupported_capability_key", kind="unprocessable")

        if "name" in updates and updates["name"] != rule.name:
            duplicate = (
                self.db.query(TenantNotificationRule)
                .filter(
                    TenantNotificationRule.tenant_id == tenant_id,
                    TenantNotificationRule.name == updates["name"],
                    TenantNotificationRule.id != rule_id,
                )
                .first()
            )
            if duplicate is not None:
                raise NotificationAdminError(code="duplicate_name", kind="conflict")

        for field_name, value in updates.items():
            setattr(rule, field_name, value)

        try:
            self._validate_rule_or_raise(rule)
        except NotificationAdminError:
            self.db.rollback()
            raise

        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise NotificationAdminError(code="duplicate_name", kind="conflict") from None
        self.db.refresh(rule)
        return rule

    def set_rule_enabled(self, *, tenant_id: str, rule_id: str, enabled: bool) -> Optional[TenantNotificationRule]:
        rule = self.get_rule(tenant_id=tenant_id, rule_id=rule_id)
        if rule is None:
            return None
        rule.enabled = enabled
        self.db.commit()
        self.db.refresh(rule)
        return rule

    def _validate_rule_or_raise(self, rule: TenantNotificationRule) -> None:
        try:
            validate_notification_rule(rule)
        except NotificationRuleConfigurationError as exc:
            raise NotificationAdminError(code=exc.code, kind="unprocessable") from None
        try:
            validate_variable_mapping(rule.variable_mapping_json)
        except NotificationVariableConfigurationError as exc:
            raise NotificationAdminError(code=exc.code, kind="unprocessable") from None

    # ------------------------------------------------------------- recipients
    def list_recipients(self, *, tenant_id: str) -> list[TenantNotificationRecipient]:
        return (
            self.db.query(TenantNotificationRecipient)
            .filter(TenantNotificationRecipient.tenant_id == tenant_id)
            .order_by(TenantNotificationRecipient.created_at.asc())
            .all()
        )

    def get_recipient(self, *, tenant_id: str, recipient_id: str) -> Optional[TenantNotificationRecipient]:
        return (
            self.db.query(TenantNotificationRecipient)
            .filter(
                TenantNotificationRecipient.tenant_id == tenant_id,
                TenantNotificationRecipient.id == recipient_id,
            )
            .first()
        )

    def create_recipient(self, *, tenant_id: str, payload) -> TenantNotificationRecipient:
        if payload.channel not in SUPPORTED_NOTIFICATION_CHANNELS:
            raise NotificationAdminError(code="unsupported_channel", kind="unprocessable")
        if payload.status not in _RECIPIENT_STATUSES:
            raise NotificationAdminError(code="unsupported_status", kind="unprocessable")

        destination = self._normalize_destination_or_raise(payload.destination)

        duplicate = (
            self.db.query(TenantNotificationRecipient)
            .filter(
                TenantNotificationRecipient.tenant_id == tenant_id,
                TenantNotificationRecipient.group_key == payload.group_key,
                TenantNotificationRecipient.channel == payload.channel,
                TenantNotificationRecipient.destination == destination,
            )
            .first()
        )
        if duplicate is not None:
            raise NotificationAdminError(code="duplicate_recipient", kind="conflict")

        recipient = TenantNotificationRecipient(
            tenant_id=tenant_id,
            group_key=payload.group_key,
            name=payload.name,
            channel=payload.channel,
            destination=destination,
            status=payload.status,
            metadata_json=payload.metadata_json,
        )
        self.db.add(recipient)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise NotificationAdminError(code="duplicate_recipient", kind="conflict") from None
        self.db.refresh(recipient)
        return recipient

    def update_recipient(
        self, *, tenant_id: str, recipient_id: str, payload
    ) -> Optional[TenantNotificationRecipient]:
        recipient = self.get_recipient(tenant_id=tenant_id, recipient_id=recipient_id)
        if recipient is None:
            return None

        updates = payload.model_dump(exclude_unset=True)
        if "status" in updates and updates["status"] not in _RECIPIENT_STATUSES:
            raise NotificationAdminError(code="unsupported_status", kind="unprocessable")
        if "destination" in updates:
            updates["destination"] = self._normalize_destination_or_raise(updates["destination"])

        for field_name, value in updates.items():
            setattr(recipient, field_name, value)

        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise NotificationAdminError(code="duplicate_recipient", kind="conflict") from None
        self.db.refresh(recipient)
        return recipient

    @staticmethod
    def _normalize_destination_or_raise(raw_destination: str) -> str:
        destination = normalize_phone(raw_destination)
        if not destination or not (_MIN_DESTINATION_LENGTH <= len(destination) <= _MAX_DESTINATION_LENGTH):
            raise NotificationAdminError(code="invalid_destination", kind="unprocessable")
        return destination

    # -------------------------------------------------------------- deliveries
    def list_deliveries(
        self,
        *,
        tenant_id: str,
        page: int,
        page_size: int,
        status: Optional[str] = None,
        event_type: Optional[str] = None,
        rule_id: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        scheduled_from: Optional[datetime] = None,
        scheduled_to: Optional[datetime] = None,
    ) -> dict[str, Any]:
        page = max(page, 1)
        page_size = min(max(page_size, 1), _MAX_PAGE_SIZE)

        query = (
            self.db.query(NotificationDelivery, TenantNotificationRule.name, DomainEvent.event_type)
            .join(TenantNotificationRule, TenantNotificationRule.id == NotificationDelivery.notification_rule_id)
            .join(DomainEvent, DomainEvent.id == NotificationDelivery.domain_event_id)
            .filter(NotificationDelivery.tenant_id == tenant_id)
        )
        if status:
            query = query.filter(NotificationDelivery.status == status)
        if rule_id:
            query = query.filter(NotificationDelivery.notification_rule_id == rule_id)
        if event_type:
            query = query.filter(DomainEvent.event_type == event_type)
        if date_from:
            query = query.filter(NotificationDelivery.created_at >= date_from)
        if date_to:
            query = query.filter(NotificationDelivery.created_at <= date_to)
        if scheduled_from:
            query = query.filter(NotificationDelivery.scheduled_for >= scheduled_from)
        if scheduled_to:
            query = query.filter(NotificationDelivery.scheduled_for <= scheduled_to)

        total = query.count()
        rows = (
            query.order_by(NotificationDelivery.created_at.desc(), NotificationDelivery.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        pages = (total + page_size - 1) // page_size if total else 0

        items = [self._delivery_item(delivery, rule_name, event_type_value) for delivery, rule_name, event_type_value in rows]
        return {"items": items, "page": page, "page_size": page_size, "total": total, "pages": pages}

    def get_delivery(self, *, tenant_id: str, delivery_id: str) -> Optional[dict[str, Any]]:
        row = (
            self.db.query(NotificationDelivery, TenantNotificationRule.name, DomainEvent.event_type)
            .join(TenantNotificationRule, TenantNotificationRule.id == NotificationDelivery.notification_rule_id)
            .join(DomainEvent, DomainEvent.id == NotificationDelivery.domain_event_id)
            .filter(NotificationDelivery.tenant_id == tenant_id, NotificationDelivery.id == delivery_id)
            .first()
        )
        if row is None:
            return None
        delivery, rule_name, event_type_value = row
        return self._delivery_item(delivery, rule_name, event_type_value)

    @staticmethod
    def _delivery_item(delivery: NotificationDelivery, rule_name: Optional[str], event_type_value: Optional[str]) -> dict[str, Any]:
        return {
            "id": delivery.id,
            "rule_id": delivery.notification_rule_id,
            "rule_name": rule_name,
            "event_type": event_type_value,
            "channel": delivery.channel,
            "recipient_masked": mask_phone(delivery.recipient),
            "template_key": delivery.template_key,
            "status": delivery.status,
            "scheduled_for": delivery.scheduled_for,
            "attempts": delivery.attempts,
            "provider_message_id": delivery.provider_message_id,
            "error_code": delivery.error_message,
            "sent_at": delivery.sent_at,
            "delivered_at": delivery.delivered_at,
            "read_at": delivery.read_at,
            "failed_at": delivery.failed_at,
            "created_at": delivery.created_at,
            "updated_at": delivery.updated_at,
        }
