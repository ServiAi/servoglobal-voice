"""Integration audit events: what may be persisted (pure)."""

from __future__ import annotations

from typing import Any

SENSITIVE_KEYS = {"api_key", "authorization", "payload", "html", "text", "base64", "phone", "email"}
MAX_MESSAGE_LENGTH = 500


def sanitize_event_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Redact sensitive keys and drop non-scalar values: provider payloads never reach the audit table."""
    sanitized: dict[str, Any] = {}
    for key, value in metadata.items():
        key_l = key.lower()
        if any(sensitive in key_l for sensitive in SENSITIVE_KEYS):
            sanitized[key] = "[redacted]"
        elif isinstance(value, (str, int, float, bool)) or value is None:
            sanitized[key] = value
        else:
            sanitized[key] = "[omitted]"
    return sanitized
