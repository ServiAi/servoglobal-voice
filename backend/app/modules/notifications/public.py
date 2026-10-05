"""Stable, import-light entry points for Notifications consumers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class NotificationTemplate:
    template_key: str
    body: str
    required_variables: tuple[str, ...]


@dataclass(frozen=True)
class NotificationMessageReceipt:
    id: str
    tenant_id: str
    template_id: str | None
    status: str
    metadata_json: dict[str, Any]
    lead_id: str | None
    contact_id: str | None
    error_message: str | None
    notification_delivery_id: str | None
    delivered_at: datetime | None
    read_at: datetime | None


@dataclass(frozen=True)
class NotificationSendResult:
    status: str
    message_id: str | None
    provider_message_id: str | None
    message: NotificationMessageReceipt | None = None


@dataclass(frozen=True)
class NotificationDeliveryEvidence:
    id: str
    status: str
    provider_message_id: str | None = None
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    created_at: datetime | None = None


def publish_booking_event(*, tenant_id: str, booking_id: str, event_type: str) -> None:
    from app.modules.notifications.runtime.event_pipeline import run_booking_notification_pipeline_task

    run_booking_notification_pipeline_task(tenant_id=tenant_id, booking_id=booking_id, event_type=event_type)


def publish_call_event(*, tenant_id: str, voice_call_id: str) -> None:
    from app.modules.notifications.runtime.event_pipeline import run_call_notification_pipeline_task

    run_call_notification_pipeline_task(tenant_id=tenant_id, voice_call_id=voice_call_id)


def report_delivery_status(
    *,
    tenant_id: str,
    provider_message_id: str,
    status: str,
    occurred_at: datetime,
    error_message: str | None = None,
) -> bool:
    from app.db.session import SessionLocal
    from app.modules.notifications.application.delivery_status_service import NotificationDeliveryStatusService

    db = SessionLocal()
    try:
        delivery = NotificationDeliveryStatusService(db).apply_provider_status(
            tenant_id=tenant_id,
            provider_message_id=provider_message_id,
            status=status,
            occurred_at=occurred_at,
            error_message=error_message,
        )
        if delivery is None:
            db.rollback()
            return False
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def delivery_exists(*, tenant_id: str, delivery_id: str) -> bool:
    from app.modules.notifications.application.delivery_status_service import delivery_exists

    return delivery_exists(tenant_id=tenant_id, delivery_id=delivery_id)


def run_worker_cli(argv: list[str] | None = None) -> int:
    from app.modules.notifications.runtime.worker import main

    return main(argv)
