from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from datetime import datetime

from sqlalchemy import func, select
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

    def summarize(
        self,
        *,
        tenant_id: str,
        providers: Sequence[str],
        event_types: Sequence[str],
        date_from: datetime,
        date_to: datetime,
        recent_limit: int = 10,
    ) -> tuple[dict[str, int], list[TenantIntegrationEvent]]:
        """Per-type counts and the most recent events of the given providers/types in a window."""
        filters = (
            TenantIntegrationEvent.tenant_id == tenant_id,
            TenantIntegrationEvent.provider.in_(tuple(providers)),
            TenantIntegrationEvent.event_type.in_(tuple(event_types)),
            TenantIntegrationEvent.created_at >= date_from,
            TenantIntegrationEvent.created_at <= date_to,
        )
        counts = dict(
            self.db.execute(
                select(TenantIntegrationEvent.event_type, func.count())
                .where(*filters)
                .group_by(TenantIntegrationEvent.event_type)
            ).all()
        )
        rows = self.db.scalars(
            select(TenantIntegrationEvent)
            .where(*filters)
            .order_by(TenantIntegrationEvent.created_at.desc())
            .limit(recent_limit)
        ).all()
        return counts, list(rows)
