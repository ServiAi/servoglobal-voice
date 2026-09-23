from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.tool_http_limits import DEFAULT_TIMEOUT_MS, MAX_TIMEOUT_MS, MIN_TIMEOUT_MS


_SENSITIVE_HEADER_NAMES = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "api-key",
        "x-auth-token",
    }
)
_SUPPORTED_INPUT_TYPES = frozenset({"string", "object", "array", "integer", "number", "boolean", "null"})


def _validate_base_url(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        parsed = urlsplit(value)
        parsed.port
    except ValueError as exc:
        raise ValueError("base_url must be a valid HTTP(S) URL.") from exc
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("base_url must be an absolute HTTP(S) URL without embedded credentials.")
    return value


def is_sensitive_header_name(name: str) -> bool:
    normalized = name.strip().lower().replace("_", "-")
    return normalized in _SENSITIVE_HEADER_NAMES or normalized.endswith(("-api-key", "-token", "-secret"))


def _validate_headers(value: dict[str, str] | None) -> dict[str, str] | None:
    if value is None:
        return None
    for name in value:
        if is_sensitive_header_name(name):
            raise ValueError(f"Sensitive header '{name}' must be configured through auth_type/secrets.")
    return value


def _validate_input_schema(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if value.get("type", "object") != "object" or not isinstance(value.get("properties", {}), dict):
        raise ValueError("input_schema must describe an object with a properties object.")
    properties = value.get("properties", {})
    required = value.get("required", [])
    if not isinstance(required, list) or not all(isinstance(key, str) for key in required):
        raise ValueError("input_schema.required must be an array of property names.")
    if not set(required).issubset(properties):
        raise ValueError("Every required input must exist in input_schema.properties.")
    for name, spec in properties.items():
        if not isinstance(name, str) or not isinstance(spec, dict) or spec.get("type") not in _SUPPORTED_INPUT_TYPES:
            raise ValueError(f"input_schema property '{name}' has an unsupported type.")
        if "enum" in spec and not isinstance(spec["enum"], list):
            raise ValueError(f"input_schema property '{name}' has an invalid enum.")
    return value


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CustomToolCreateRequest(_StrictModel):
    """Everything needed to create a Custom HTTP Tool in one call --
    `secrets` (if `auth_type != "none"`) is write-only and never echoed
    back by any response schema in this module."""

    key: str = Field(min_length=1, max_length=90)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=2000)
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    base_url: str = Field(min_length=1, max_length=2048)
    path_template: str = Field(default="/", max_length=1024)
    timeout_ms: int = Field(default=DEFAULT_TIMEOUT_MS, ge=MIN_TIMEOUT_MS, le=MAX_TIMEOUT_MS)
    headers: dict[str, str] = Field(default_factory=dict)
    path_mapping: dict[str, str] = Field(default_factory=dict)
    query_mapping: dict[str, str] = Field(default_factory=dict)
    body_mapping: dict[str, str] = Field(default_factory=dict)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    response_mapping: dict[str, str] = Field(default_factory=dict)
    auth_type: Literal["none", "bearer", "api_key", "basic"] = "none"
    api_key_header_name: str | None = Field(default=None, max_length=80)
    secrets: dict[str, str] | None = None

    _base_url_is_valid = field_validator("base_url")(_validate_base_url)
    _headers_are_safe = field_validator("headers")(_validate_headers)
    _input_schema_is_supported = field_validator("input_schema")(_validate_input_schema)


class CustomToolUpdateRequest(_StrictModel):
    """Partial update -- `key` is immutable after creation and not
    included here. Omitted fields keep their current value; `secrets`
    omitted/None means "keep the existing credential"."""

    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] | None = None
    base_url: str | None = Field(default=None, min_length=1, max_length=2048)
    path_template: str | None = Field(default=None, max_length=1024)
    timeout_ms: int | None = Field(default=None, ge=MIN_TIMEOUT_MS, le=MAX_TIMEOUT_MS)
    headers: dict[str, str] | None = None
    path_mapping: dict[str, str] | None = None
    query_mapping: dict[str, str] | None = None
    body_mapping: dict[str, str] | None = None
    input_schema: dict[str, Any] | None = None
    response_mapping: dict[str, str] | None = None
    auth_type: Literal["none", "bearer", "api_key", "basic"] | None = None
    api_key_header_name: str | None = Field(default=None, max_length=80)
    secrets: dict[str, str] | None = None

    _base_url_is_valid = field_validator("base_url")(_validate_base_url)
    _headers_are_safe = field_validator("headers")(_validate_headers)
    _input_schema_is_supported = field_validator("input_schema")(_validate_input_schema)


class CredentialMaskedResponse(_StrictModel):
    auth_type: Literal["none", "bearer", "api_key", "basic"]
    configured: bool
    api_key_header_name: str | None
    masked_fields: dict[str, str] = Field(default_factory=dict)


class CustomToolResponse(_StrictModel):
    id: str
    tenant_id: str
    key: str
    name: str
    description: str
    status: Literal["active", "disabled"]
    method: str
    base_url: str
    path_template: str
    timeout_ms: int
    headers: dict[str, str]
    path_mapping: dict[str, str]
    query_mapping: dict[str, str]
    body_mapping: dict[str, str]
    input_schema: dict[str, Any]
    response_mapping: dict[str, str]
    credential: CredentialMaskedResponse
    created_at: datetime
    updated_at: datetime


class CustomToolTestRequest(_StrictModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class CustomToolTestResponse(_StrictModel):
    success: bool
    status_code: int | None = None
    latency_ms: int | None = None
    mapped_result: dict[str, Any] | None = None
    error_code: str | None = None
