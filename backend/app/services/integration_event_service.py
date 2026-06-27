from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.integrations import TenantIntegrationEvent

SENSITIVE_KEYS = {"api_key", "authorization", "payload", "html", "text", "base64", "phone", "email"}


class IntegrationEventService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record_event(
        self,
        *,
        tenant_id: str,
        provider: str,
        event_type: str,
        status: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TenantIntegrationEvent:
        event = TenantIntegrationEvent(
            tenant_id=tenant_id,
            provider=provider,
            event_type=event_type,
            status=status,
            resource_type=resource_type,
            resource_id=resource_id,
            message=message[:500] if message else None,
            metadata_json=self._sanitize_metadata(metadata or {}),
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def _sanitize_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
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
