from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.modules.integrations.domain.events import MAX_MESSAGE_LENGTH, sanitize_event_metadata
from app.modules.integrations.infrastructure.models import TenantIntegrationEvent

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
        event = self.add_event(
            tenant_id=tenant_id,
            provider=provider,
            event_type=event_type,
            status=status,
            resource_type=resource_type,
            resource_id=resource_id,
            message=message,
            metadata=metadata,
        )
        self.db.commit()
        self.db.refresh(event)
        return event

    def add_event(
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
        """Same event as record_event but part of the caller's transaction
        (added, not committed)."""
        event = TenantIntegrationEvent(
            tenant_id=tenant_id,
            provider=provider,
            event_type=event_type,
            status=status,
            resource_type=resource_type,
            resource_id=resource_id,
            message=message[:MAX_MESSAGE_LENGTH] if message else None,
            metadata_json=sanitize_event_metadata(metadata or {}),
        )
        self.db.add(event)
        return event
