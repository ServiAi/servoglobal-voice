from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domain.notification_variables import (
    NotificationVariableFormat,
    NotificationVariableMappingError,
    NotificationVariableSource,
    NotificationVariableSpec,
    validate_variable_mapping,
)

_MISSING = object()
_SKIP = object()

_DATE_ISO_FMT = "%Y-%m-%d"
_DATE_DMY_FMT = "%d/%m/%Y"
_TIME_24H_FMT = "%H:%M"
_DATETIME_DMY_24H_FMT = "%d/%m/%Y %H:%M"


def _resolve_path(payload: dict, path: str) -> Any:
    current: Any = payload
    for segment in path.split("."):
        if not isinstance(current, dict) or segment not in current:
            return _MISSING
        current = current[segment]
    return current


class NotificationVariableMapper:
    def map_variables(
        self,
        *,
        tenant_id: str,
        rule_id: str,
        mapping: dict,
        payload: dict,
    ) -> dict[str, str]:
        specs = validate_variable_mapping(mapping)

        result: dict[str, str] = {}
        for key, spec in specs.items():
            value = self._resolve_value(tenant_id=tenant_id, rule_id=rule_id, spec=spec, payload=payload)
            if value is _SKIP:
                continue
            result[key] = self._format_value(
                tenant_id=tenant_id, rule_id=rule_id, spec=spec, value=value, payload=payload
            )
        return result

    def _resolve_value(
        self,
        *,
        tenant_id: str,
        rule_id: str,
        spec: NotificationVariableSpec,
        payload: dict,
    ) -> Any:
        if spec.source == NotificationVariableSource.LITERAL:
            if spec.value is not None:
                return spec.value
            return _SKIP

        raw = _resolve_path(payload, spec.path) if spec.path else _MISSING
        if raw is _MISSING or raw is None:
            if spec.default is not None:
                return spec.default
            if spec.required:
                raise NotificationVariableMappingError(
                    tenant_id=tenant_id, rule_id=rule_id, code="required_field_missing"
                )
            return _SKIP

        if isinstance(raw, (dict, list, bytes)):
            raise NotificationVariableMappingError(
                tenant_id=tenant_id, rule_id=rule_id, code="field_value_type_not_allowed"
            )
        if not isinstance(raw, (str, int, float, bool)):
            raise NotificationVariableMappingError(
                tenant_id=tenant_id, rule_id=rule_id, code="field_value_type_not_allowed"
            )
        return raw

    def _format_value(
        self,
        *,
        tenant_id: str,
        rule_id: str,
        spec: NotificationVariableSpec,
        value: Any,
        payload: dict,
    ) -> str:
        if spec.format == NotificationVariableFormat.STRING:
            return str(value)

        dt = self._parse_datetime(tenant_id=tenant_id, rule_id=rule_id, value=value)
        dt = self._resolve_timezone(tenant_id=tenant_id, rule_id=rule_id, spec=spec, dt=dt, payload=payload)

        if spec.format == NotificationVariableFormat.DATE_ISO:
            return dt.strftime(_DATE_ISO_FMT)
        if spec.format == NotificationVariableFormat.DATE_DMY:
            return dt.strftime(_DATE_DMY_FMT)
        if spec.format == NotificationVariableFormat.TIME_24H:
            return dt.strftime(_TIME_24H_FMT)
        if spec.format == NotificationVariableFormat.DATETIME_ISO:
            return dt.isoformat()
        if spec.format == NotificationVariableFormat.DATETIME_DMY_24H:
            return dt.strftime(_DATETIME_DMY_24H_FMT)
        raise NotificationVariableMappingError(tenant_id=tenant_id, rule_id=rule_id, code="unsupported_format")

    def _parse_datetime(self, *, tenant_id: str, rule_id: str, value: Any) -> datetime:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value)
            except ValueError:
                raise NotificationVariableMappingError(
                    tenant_id=tenant_id, rule_id=rule_id, code="invalid_datetime_format"
                ) from None
        else:
            raise NotificationVariableMappingError(
                tenant_id=tenant_id, rule_id=rule_id, code="invalid_datetime_format"
            )

        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            raise NotificationVariableMappingError(
                tenant_id=tenant_id, rule_id=rule_id, code="datetime_naive_not_allowed"
            )
        return dt

    def _resolve_timezone(
        self,
        *,
        tenant_id: str,
        rule_id: str,
        spec: NotificationVariableSpec,
        dt: datetime,
        payload: dict,
    ) -> datetime:
        tz_name: str | None = None
        if spec.timezone:
            tz_name = spec.timezone
        elif spec.timezone_path:
            raw_tz = _resolve_path(payload, spec.timezone_path)
            if raw_tz is _MISSING or not isinstance(raw_tz, str) or not raw_tz:
                raise NotificationVariableMappingError(
                    tenant_id=tenant_id, rule_id=rule_id, code="timezone_path_value_invalid"
                )
            tz_name = raw_tz

        if tz_name is None:
            return dt

        try:
            zone = ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, ValueError):
            raise NotificationVariableMappingError(
                tenant_id=tenant_id, rule_id=rule_id, code="invalid_timezone"
            ) from None
        return dt.astimezone(zone)
