from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.events import validate_domain_event_payload
from app.models.notifications import DomainEvent

_MAX_SOURCE_LENGTH = 80
_MAX_IDEMPOTENCY_KEY_LENGTH = 255
_MAX_RESOURCE_TYPE_LENGTH = 80
_MAX_RESOURCE_ID_LENGTH = 80
_MAX_CORRELATION_ID_LENGTH = 255


class DomainEventIdempotencyConflictError(ValueError):
    def __init__(self, *, tenant_id: str, idempotency_key: str) -> None:
        super().__init__(
            f"Idempotency conflict for tenant_id={tenant_id} idempotency_key={idempotency_key}"
        )
        self.tenant_id = tenant_id
        self.idempotency_key = idempotency_key


@dataclass(frozen=True)
class DomainEventPublishResult:
    event: DomainEvent
    created: bool


class DomainEventService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def publish(
        self,
        *,
        tenant_id: str,
        event_type: str,
        source: str,
        idempotency_key: str,
        payload: dict[str, Any],
        resource_type: str | None = None,
        resource_id: str | None = None,
        correlation_id: str | None = None,
        available_at: datetime | None = None,
    ) -> DomainEventPublishResult:
        self._validate_publish_arguments(
            tenant_id=tenant_id,
            source=source,
            idempotency_key=idempotency_key,
            resource_type=resource_type,
            resource_id=resource_id,
            correlation_id=correlation_id,
            available_at=available_at,
        )

        normalized_payload = validate_domain_event_payload(event_type, payload)

        existing = self.get_by_idempotency_key(tenant_id=tenant_id, idempotency_key=idempotency_key)
        if existing is not None:
            return self._reconcile_existing(
                existing,
                event_type=event_type,
                source=source,
                resource_type=resource_type,
                resource_id=resource_id,
                correlation_id=correlation_id,
                payload=normalized_payload,
            )

        event = DomainEvent(
            tenant_id=tenant_id,
            event_type=event_type,
            source=source,
            resource_type=resource_type,
            resource_id=resource_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            payload_json=normalized_payload,
            status="pending",
            attempts=0,
        )
        if available_at is not None:
            event.available_at = available_at

        self.db.add(event)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self.get_by_idempotency_key(
                tenant_id=tenant_id, idempotency_key=idempotency_key
            )
            if existing is not None:
                return self._reconcile_existing(
                    existing,
                    event_type=event_type,
                    source=source,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    correlation_id=correlation_id,
                    payload=normalized_payload,
                )
            raise

        self.db.refresh(event)
        return DomainEventPublishResult(event=event, created=True)

    def get_event(self, *, tenant_id: str, event_id: str) -> DomainEvent | None:
        return (
            self.db.query(DomainEvent)
            .filter(DomainEvent.tenant_id == tenant_id, DomainEvent.id == event_id)
            .first()
        )

    def get_by_idempotency_key(
        self, *, tenant_id: str, idempotency_key: str
    ) -> DomainEvent | None:
        return (
            self.db.query(DomainEvent)
            .filter(
                DomainEvent.tenant_id == tenant_id,
                DomainEvent.idempotency_key == idempotency_key,
            )
            .first()
        )

    def _reconcile_existing(
        self,
        existing: DomainEvent,
        *,
        event_type: str,
        source: str,
        resource_type: str | None,
        resource_id: str | None,
        correlation_id: str | None,
        payload: dict[str, Any],
    ) -> DomainEventPublishResult:
        if self._is_equivalent(
            existing,
            event_type=event_type,
            source=source,
            resource_type=resource_type,
            resource_id=resource_id,
            correlation_id=correlation_id,
            payload=payload,
        ):
            return DomainEventPublishResult(event=existing, created=False)
        raise DomainEventIdempotencyConflictError(
            tenant_id=existing.tenant_id, idempotency_key=existing.idempotency_key
        )

    @staticmethod
    def _is_equivalent(
        existing: DomainEvent,
        *,
        event_type: str,
        source: str,
        resource_type: str | None,
        resource_id: str | None,
        correlation_id: str | None,
        payload: dict[str, Any],
    ) -> bool:
        return (
            existing.event_type == event_type
            and existing.source == source
            and existing.resource_type == resource_type
            and existing.resource_id == resource_id
            and existing.correlation_id == correlation_id
            and existing.payload_json == payload
        )

    @staticmethod
    def _validate_publish_arguments(
        *,
        tenant_id: str,
        source: str,
        idempotency_key: str,
        resource_type: str | None,
        resource_id: str | None,
        correlation_id: str | None,
        available_at: datetime | None,
    ) -> None:
        if not tenant_id:
            raise ValueError("tenant_id is required")
        if not source or len(source) > _MAX_SOURCE_LENGTH:
            raise ValueError("source is required and must be at most 80 characters")
        if not idempotency_key or len(idempotency_key) > _MAX_IDEMPOTENCY_KEY_LENGTH:
            raise ValueError("idempotency_key is required and must be at most 255 characters")
        if resource_type is not None and len(resource_type) > _MAX_RESOURCE_TYPE_LENGTH:
            raise ValueError("resource_type must be at most 80 characters")
        if resource_id is not None and len(resource_id) > _MAX_RESOURCE_ID_LENGTH:
            raise ValueError("resource_id must be at most 80 characters")
        if correlation_id is not None and len(correlation_id) > _MAX_CORRELATION_ID_LENGTH:
            raise ValueError("correlation_id must be at most 255 characters")
        if available_at is not None and (
            available_at.tzinfo is None or available_at.tzinfo.utcoffset(available_at) is None
        ):
            raise ValueError("available_at must be timezone-aware")
