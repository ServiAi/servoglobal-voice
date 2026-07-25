from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.domain.notification_rules import NotificationRecipientResolutionError, validate_field_path
from app.models.notifications import TenantNotificationRecipient, TenantNotificationRule

_MIN_DESTINATION_LENGTH = 8
_MAX_DESTINATION_LENGTH = 32


def _resolve_dict_path(payload: dict, field: str) -> Any:
    current: Any = payload
    for segment in field.split("."):
        if not isinstance(current, dict) or segment not in current:
            return None
        current = current[segment]
    return current


def _normalize_whatsapp_destination(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    candidate = raw.strip()
    if not candidate:
        return None
    if len(candidate) < _MIN_DESTINATION_LENGTH or len(candidate) > _MAX_DESTINATION_LENGTH:
        return None
    return candidate


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


class NotificationRecipientService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def resolve(
        self, *, tenant_id: str, rule: TenantNotificationRule, payload: dict
    ) -> list[str]:
        strategy = rule.recipient_strategy

        if strategy == "event_customer":
            destination = _normalize_whatsapp_destination(_resolve_dict_path(payload, "customer.phone"))
            return [destination] if destination else []

        if strategy == "configured_group":
            return self._resolve_configured_group(tenant_id=tenant_id, rule=rule)

        if strategy == "event_field":
            if not rule.recipient_group_key:
                raise NotificationRecipientResolutionError(
                    tenant_id=tenant_id, rule_id=rule.id, code="recipient_group_key_missing"
                )
            try:
                validate_field_path(rule.recipient_group_key)
            except ValueError:
                raise NotificationRecipientResolutionError(
                    tenant_id=tenant_id, rule_id=rule.id, code="invalid_event_field_path"
                ) from None
            destination = _normalize_whatsapp_destination(
                _resolve_dict_path(payload, rule.recipient_group_key)
            )
            return [destination] if destination else []

        raise NotificationRecipientResolutionError(
            tenant_id=tenant_id, rule_id=rule.id, code="unsupported_recipient_strategy"
        )

    def _resolve_configured_group(
        self, *, tenant_id: str, rule: TenantNotificationRule
    ) -> list[str]:
        rows = (
            self.db.query(TenantNotificationRecipient)
            .filter(
                TenantNotificationRecipient.tenant_id == tenant_id,
                TenantNotificationRecipient.group_key == rule.recipient_group_key,
                TenantNotificationRecipient.channel == rule.channel,
                TenantNotificationRecipient.status == "active",
            )
            .order_by(
                TenantNotificationRecipient.created_at.asc(),
                TenantNotificationRecipient.id.asc(),
            )
            .all()
        )
        destinations = [
            destination
            for destination in (
                _normalize_whatsapp_destination(row.destination) for row in rows
            )
            if destination
        ]
        return _dedupe_preserve_order(destinations)
