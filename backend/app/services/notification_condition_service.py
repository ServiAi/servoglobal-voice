from __future__ import annotations

from typing import Any

from app.domain.notification_rules import (
    NotificationCondition,
    NotificationConditionEvaluationError,
    NotificationConditionOperator,
)

_MISSING = object()


def _resolve_path(payload: dict, field: str) -> Any:
    current: Any = payload
    for segment in field.split("."):
        if not isinstance(current, dict) or segment not in current:
            return _MISSING
        current = current[segment]
    return current


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (str, list, dict)):
        return len(value) == 0
    return False


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class NotificationConditionService:
    def matches(self, *, conditions: list[NotificationCondition], payload: dict) -> bool:
        return all(self._evaluate(condition, payload) for condition in conditions)

    def _evaluate(self, condition: NotificationCondition, payload: dict) -> bool:
        value = _resolve_path(payload, condition.field)
        exists = value is not _MISSING
        operator = condition.operator

        if operator == NotificationConditionOperator.EXISTS:
            return exists
        if operator == NotificationConditionOperator.NOT_EXISTS:
            return not exists
        if operator == NotificationConditionOperator.NOT_EMPTY:
            return exists and not _is_empty(value)

        if not exists:
            return operator in (
                NotificationConditionOperator.NOT_EQUALS,
                NotificationConditionOperator.NOT_IN,
            )

        if operator == NotificationConditionOperator.EQUALS:
            return value == condition.value
        if operator == NotificationConditionOperator.NOT_EQUALS:
            return value != condition.value
        if operator == NotificationConditionOperator.IN:
            return value in condition.value
        if operator == NotificationConditionOperator.NOT_IN:
            return value not in condition.value

        if operator in (
            NotificationConditionOperator.GREATER_THAN,
            NotificationConditionOperator.GREATER_THAN_OR_EQUAL,
            NotificationConditionOperator.LESS_THAN,
            NotificationConditionOperator.LESS_THAN_OR_EQUAL,
        ):
            if not _is_number(value) or not _is_number(condition.value):
                raise NotificationConditionEvaluationError(
                    code="non_numeric_comparison", field=condition.field
                )
            if operator == NotificationConditionOperator.GREATER_THAN:
                return value > condition.value
            if operator == NotificationConditionOperator.GREATER_THAN_OR_EQUAL:
                return value >= condition.value
            if operator == NotificationConditionOperator.LESS_THAN:
                return value < condition.value
            return value <= condition.value

        raise NotificationConditionEvaluationError(code="unsupported_operator", field=condition.field)
