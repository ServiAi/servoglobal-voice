from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, ValidationError as PydanticValidationError
from pydantic import model_validator

from app.domain.notification_rules import validate_field_path

_MAX_VARIABLES = 50
_MAX_KEY_LENGTH = 80
_MAX_TIMEZONE_LENGTH = 80

_LiteralValue = str | int | float | bool


class NotificationVariableSource(str, Enum):
    EVENT_FIELD = "event_field"
    LITERAL = "literal"


class NotificationVariableFormat(str, Enum):
    STRING = "string"
    DATE_ISO = "date_iso"
    DATE_DMY = "date_dmy"
    TIME_24H = "time_24h"
    DATETIME_ISO = "datetime_iso"
    DATETIME_DMY_24H = "datetime_dmy_24h"


class NotificationVariableConfigurationError(ValueError):
    def __init__(self, *, code: str) -> None:
        super().__init__(f"Invalid notification variable configuration code={code}")
        self.code = code


class NotificationVariableMappingError(ValueError):
    def __init__(self, *, tenant_id: str, rule_id: str, code: str) -> None:
        super().__init__(
            f"Notification variable mapping error tenant_id={tenant_id} rule_id={rule_id} code={code}"
        )
        self.tenant_id = tenant_id
        self.rule_id = rule_id
        self.code = code


class NotificationVariableSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: NotificationVariableSource
    path: str | None = None
    value: _LiteralValue | None = None
    format: NotificationVariableFormat = NotificationVariableFormat.STRING
    timezone: str | None = Field(None, max_length=_MAX_TIMEZONE_LENGTH)
    timezone_path: str | None = None
    required: bool = True
    default: _LiteralValue | None = None

    @model_validator(mode="after")
    def _validate_spec(self) -> "NotificationVariableSpec":
        if self.source == NotificationVariableSource.EVENT_FIELD:
            if not self.path:
                raise ValueError("event_field_requires_path")
        elif self.source == NotificationVariableSource.LITERAL:
            if self.path is not None:
                raise ValueError("literal_forbids_path")
            if self.value is None and self.required:
                raise ValueError("literal_requires_value")

        if self.timezone is not None and self.timezone_path is not None:
            raise ValueError("timezone_and_timezone_path_conflict")

        if self.path is not None:
            try:
                validate_field_path(self.path)
            except ValueError:
                raise ValueError("path_invalid") from None

        if self.timezone_path is not None:
            try:
                validate_field_path(self.timezone_path)
            except ValueError:
                raise ValueError("timezone_path_invalid") from None

        return self


def validate_variable_mapping(mapping: dict) -> dict[str, NotificationVariableSpec]:
    if not isinstance(mapping, dict):
        raise NotificationVariableConfigurationError(code="mapping_must_be_dict")
    if len(mapping) > _MAX_VARIABLES:
        raise NotificationVariableConfigurationError(code="mapping_too_many_variables")

    result: dict[str, NotificationVariableSpec] = {}
    for key, raw_spec in mapping.items():
        if not isinstance(key, str):
            raise NotificationVariableConfigurationError(code="mapping_key_must_be_string")
        if not key:
            raise NotificationVariableConfigurationError(code="mapping_key_empty")
        if len(key) > _MAX_KEY_LENGTH:
            raise NotificationVariableConfigurationError(code="mapping_key_too_long")
        try:
            spec = NotificationVariableSpec.model_validate(raw_spec)
        except PydanticValidationError:
            raise NotificationVariableConfigurationError(code="variable_spec_invalid") from None
        result[key] = spec
    return result
