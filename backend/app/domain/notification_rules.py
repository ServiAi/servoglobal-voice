from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError
from pydantic import model_validator

if TYPE_CHECKING:
    from app.models.notifications import TenantNotificationRule

SUPPORTED_NOTIFICATION_CHANNELS = {"whatsapp"}

SUPPORTED_NOTIFICATION_ACTIONS = {
    "send_whatsapp_template",
}

SUPPORTED_RECIPIENT_STRATEGIES = {
    "event_customer",
    "configured_group",
    "event_field",
}

SUPPORTED_SCHEDULE_MODES = {
    "immediate",
    "relative_to_booking",
}

_FIELD_MAX_LENGTH = 160
_ALLOWED_FIELD_ROOTS = {"booking", "call", "customer", "lead", "custom"}
_FORBIDDEN_FIELD_SEGMENTS = {"__class__", "__dict__", "__globals__", "__mro__", "__subclasses__"}


class NotificationConditionOperator(str, Enum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN = "in"
    NOT_IN = "not_in"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"
    NOT_EMPTY = "not_empty"
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    LESS_THAN = "less_than"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"


_COMPARISON_OPERATORS = frozenset(
    {
        NotificationConditionOperator.GREATER_THAN,
        NotificationConditionOperator.GREATER_THAN_OR_EQUAL,
        NotificationConditionOperator.LESS_THAN,
        NotificationConditionOperator.LESS_THAN_OR_EQUAL,
    }
)
_VALUE_REQUIRED_OPERATORS = frozenset(
    {NotificationConditionOperator.EQUALS, NotificationConditionOperator.NOT_EQUALS} | _COMPARISON_OPERATORS
)
_VALUE_LIST_OPERATORS = frozenset(
    {NotificationConditionOperator.IN, NotificationConditionOperator.NOT_IN}
)


def validate_field_path(value: str) -> str:
    if not value:
        raise ValueError("field_path_required")
    if len(value) > _FIELD_MAX_LENGTH:
        raise ValueError("field_path_too_long")

    segments = value.split(".")
    if any(segment == "" for segment in segments):
        raise ValueError("field_path_empty_segment")
    if segments[0] not in _ALLOWED_FIELD_ROOTS:
        raise ValueError("field_path_invalid_root")

    for segment in segments:
        if segment in _FORBIDDEN_FIELD_SEGMENTS:
            raise ValueError("field_path_forbidden_segment")
        if segment.startswith("_"):
            raise ValueError("field_path_segment_starts_with_underscore")
        if segment.isdigit():
            raise ValueError("field_path_list_index_not_allowed")
        if not all(ch.isalnum() or ch == "_" for ch in segment):
            raise ValueError("field_path_invalid_characters")

    return value


class NotificationCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str = Field(..., max_length=_FIELD_MAX_LENGTH)
    operator: NotificationConditionOperator
    value: Any | None = None

    @model_validator(mode="after")
    def _validate_condition(self) -> NotificationCondition:
        validate_field_path(self.field)

        if self.operator in _VALUE_LIST_OPERATORS:
            if not isinstance(self.value, list):
                raise ValueError("condition_value_must_be_list")
        elif self.operator in _VALUE_REQUIRED_OPERATORS:
            if self.value is None:
                raise ValueError("condition_value_required")
        return self


class NotificationRuleConfigurationError(ValueError):
    def __init__(self, *, tenant_id: str, rule_id: str, code: str) -> None:
        super().__init__(
            f"Invalid notification rule configuration tenant_id={tenant_id} rule_id={rule_id} code={code}"
        )
        self.tenant_id = tenant_id
        self.rule_id = rule_id
        self.code = code


class NotificationConditionEvaluationError(ValueError):
    def __init__(self, *, code: str, field: str | None = None) -> None:
        message = f"Notification condition evaluation error code={code}"
        if field:
            message = f"{message} field={field}"
        super().__init__(message)
        self.code = code
        self.field = field


class NotificationRecipientResolutionError(ValueError):
    def __init__(self, *, tenant_id: str, rule_id: str, code: str) -> None:
        super().__init__(
            f"Notification recipient resolution error tenant_id={tenant_id} rule_id={rule_id} code={code}"
        )
        self.tenant_id = tenant_id
        self.rule_id = rule_id
        self.code = code


class NotificationEventProcessingError(RuntimeError):
    def __init__(self, *, tenant_id: str, event_id: str, code: str) -> None:
        super().__init__(
            f"Notification event processing error tenant_id={tenant_id} event_id={event_id} code={code}"
        )
        self.tenant_id = tenant_id
        self.event_id = event_id
        self.code = code


def validate_notification_rule(rule: TenantNotificationRule) -> list[NotificationCondition]:
    tenant_id = rule.tenant_id
    rule_id = rule.id

    def _fail(code: str) -> NotificationRuleConfigurationError:
        return NotificationRuleConfigurationError(tenant_id=tenant_id, rule_id=rule_id, code=code)

    if rule.channel not in SUPPORTED_NOTIFICATION_CHANNELS:
        raise _fail("unsupported_channel")
    if rule.action_type not in SUPPORTED_NOTIFICATION_ACTIONS:
        raise _fail("unsupported_action_type")
    if not rule.template_key or not rule.template_key.strip():
        raise _fail("template_key_required")

    if rule.recipient_strategy not in SUPPORTED_RECIPIENT_STRATEGIES:
        raise _fail("unsupported_recipient_strategy")

    if rule.recipient_strategy == "configured_group":
        if not rule.recipient_group_key:
            raise _fail("recipient_group_key_required")
    elif rule.recipient_strategy == "event_field":
        if not rule.recipient_group_key:
            raise _fail("recipient_group_key_required")
        try:
            validate_field_path(rule.recipient_group_key)
        except ValueError:
            raise _fail("recipient_group_key_invalid_path") from None

    if rule.schedule_mode not in SUPPORTED_SCHEDULE_MODES:
        raise _fail("unsupported_schedule_mode")
    if rule.schedule_mode == "immediate" and rule.schedule_offset_minutes != 0:
        raise _fail("immediate_requires_zero_offset")
    if rule.schedule_mode == "relative_to_booking" and not rule.event_type.startswith("booking."):
        raise _fail("relative_to_booking_requires_booking_event")

    if not isinstance(rule.conditions_json, list):
        raise _fail("conditions_must_be_list")

    conditions: list[NotificationCondition] = []
    for raw_condition in rule.conditions_json:
        try:
            conditions.append(NotificationCondition.model_validate(raw_condition))
        except PydanticValidationError:
            raise _fail("condition_invalid") from None

    if not isinstance(rule.variable_mapping_json, dict):
        raise _fail("variable_mapping_must_be_dict")

    return conditions
