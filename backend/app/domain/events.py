from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError as PydanticValidationError
from pydantic import field_validator, model_validator

_MAX_CUSTOM_DEPTH = 5
_MAX_PAYLOAD_BYTES = 32 * 1024

_SENSITIVE_KEY_RAW_TOKENS = (
    "authorization",
    "bearer",
    "api_key",
    "apikey",
    "access_token",
    "accesstoken",
    "refresh_token",
    "refreshtoken",
    "client_secret",
    "clientsecret",
    "app_secret",
    "appsecret",
    "webhook_secret",
    "webhooksecret",
    "voice_tool_shared_secret",
    "raw_payload",
    "rawpayload",
    "payload_data",
    "payloaddata",
    "base64",
    "html",
    "attachment",
    "attachments",
    "recording",
    "recording_url",
    "transcript",
    "transcript_url",
)


def _normalize_key(key: str) -> str:
    return "".join(ch for ch in key.lower() if ch.isalnum())


_SENSITIVE_KEY_TOKENS = frozenset(_normalize_key(token) for token in _SENSITIVE_KEY_RAW_TOKENS)


def _is_sensitive_key(key: str) -> bool:
    return _normalize_key(key) in _SENSITIVE_KEY_TOKENS


class DomainEventType(str, Enum):
    BOOKING_CREATED = "booking.created"
    BOOKING_CANCELLED = "booking.cancelled"
    BOOKING_RESCHEDULED = "booking.rescheduled"
    CALL_COMPLETED = "call.completed"
    CALL_FAILED = "call.failed"
    CALL_NO_ANSWER = "call.no_answer"


SUPPORTED_DOMAIN_EVENT_TYPES = frozenset(event_type.value for event_type in DomainEventType)


class UnsupportedDomainEventTypeError(ValueError):
    def __init__(self, event_type: str) -> None:
        super().__init__(f"Unsupported domain event type: {event_type}")
        self.event_type = event_type


class DomainEventPayloadValidationError(ValueError):
    def __init__(self, *, event_type: str, location: str, error_type: str) -> None:
        super().__init__(
            f"Invalid payload for event_type={event_type} at location={location} ({error_type})"
        )
        self.event_type = event_type
        self.location = location
        self.error_type = error_type


def _check_json_safe(value: Any, *, depth: int) -> None:
    if isinstance(value, (list, dict)):
        if depth > _MAX_CUSTOM_DEPTH:
            raise ValueError("custom_max_depth_exceeded")
        if isinstance(value, list):
            for item in value:
                _check_json_safe(item, depth=depth + 1)
        else:
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ValueError("custom_invalid_key_type")
                if _is_sensitive_key(key):
                    raise ValueError("custom_sensitive_key")
                _check_json_safe(item, depth=depth + 1)
        return
    if value is None or isinstance(value, (bool, int, float, str)):
        return
    raise ValueError("custom_invalid_value_type")


class EventCustomer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=80)
    email: str | None = Field(None, max_length=255)

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> EventCustomer:
        if self.name is None and self.phone is None and self.email is None:
            raise ValueError("customer_requires_at_least_one_field")
        return self


class EventLead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., max_length=36)
    status: str | None = Field(None, max_length=40)


class EventCallReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., max_length=36)
    provider_call_id: str | None = Field(None, max_length=255)


def _require_timezone_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError("datetime_naive_not_allowed")
    return value


class BookingEventData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., max_length=36)
    status: str = Field(..., max_length=32)
    title: str | None = Field(None, max_length=255)
    start_at: datetime
    end_at: datetime | None = None
    timezone: str = Field(..., max_length=80)
    meeting_url: str | None = Field(None, max_length=500)

    @field_validator("start_at")
    @classmethod
    def _validate_start_at(cls, value: datetime) -> datetime:
        return _require_timezone_aware(value)

    @field_validator("end_at")
    @classmethod
    def _validate_end_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        return _require_timezone_aware(value)

    @model_validator(mode="after")
    def _validate_range(self) -> BookingEventData:
        if self.end_at is not None and self.end_at < self.start_at:
            raise ValueError("end_at_before_start_at")
        return self


class VoiceCallEventData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., max_length=36)
    provider: str = Field(..., max_length=40)
    provider_call_id: str | None = Field(None, max_length=255)
    status: str = Field(..., max_length=32)
    duration_seconds: int | None = Field(None, ge=0)
    summary: str | None = Field(None, max_length=4000)
    outcome: str | None = Field(None, max_length=80)


def _validate_custom_field(value: dict[str, Any]) -> dict[str, Any]:
    _check_json_safe(value, depth=1)
    return value


class BookingEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    booking: BookingEventData
    customer: EventCustomer | None = None
    lead: EventLead | None = None
    call: EventCallReference | None = None
    custom: dict[str, Any] = Field(default_factory=dict)

    @field_validator("custom")
    @classmethod
    def _validate_custom(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_custom_field(value)


class CallEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call: VoiceCallEventData
    customer: EventCustomer | None = None
    lead: EventLead | None = None
    custom: dict[str, Any] = Field(default_factory=dict)

    @field_validator("custom")
    @classmethod
    def _validate_custom(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_custom_field(value)


EVENT_PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    DomainEventType.BOOKING_CREATED.value: BookingEventPayload,
    DomainEventType.BOOKING_CANCELLED.value: BookingEventPayload,
    DomainEventType.BOOKING_RESCHEDULED.value: BookingEventPayload,
    DomainEventType.CALL_COMPLETED.value: CallEventPayload,
    DomainEventType.CALL_FAILED.value: CallEventPayload,
    DomainEventType.CALL_NO_ANSWER.value: CallEventPayload,
}


def validate_domain_event_payload(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise DomainEventPayloadValidationError(
            event_type=event_type, location="root", error_type="invalid_payload_type"
        )

    model_cls = EVENT_PAYLOAD_MODELS.get(event_type)
    if model_cls is None:
        raise UnsupportedDomainEventTypeError(event_type)

    try:
        model = model_cls.model_validate(payload)
    except PydanticValidationError as exc:
        first_error = exc.errors()[0]
        location = ".".join(str(part) for part in first_error.get("loc", ())) or "root"
        raise DomainEventPayloadValidationError(
            event_type=event_type,
            location=location,
            error_type=first_error.get("type", "value_error"),
        ) from None

    normalized = model.model_dump(mode="json", exclude_none=True)

    serialized_size = len(
        json.dumps(normalized, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    if serialized_size > _MAX_PAYLOAD_BYTES:
        raise DomainEventPayloadValidationError(
            event_type=event_type, location="custom", error_type="payload_too_large"
        )

    return normalized
