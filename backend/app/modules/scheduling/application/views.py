"""ORM -> DTO/plain-dict translation. Routers and facades call these so they
never navigate Scheduling rows themselves."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.scheduling.domain.contracts import BookingView
from app.modules.scheduling.infrastructure.models import (
    CrmBooking,
    TenantAgentSchedulingConfig,
    TenantSchedulingAvailabilityException,
    TenantSchedulingEventType,
    TenantSchedulingResource,
    TenantSchedulingSchedule,
    TenantSchedulingTeam,
)


def _notification_custom(metadata_json: Any) -> dict[str, Any]:
    """The only booking-metadata key Notifications may read."""
    if not isinstance(metadata_json, dict):
        return {}
    custom = metadata_json.get("notification_custom")
    return dict(custom) if isinstance(custom, dict) else {}


def booking_view(b: CrmBooking) -> BookingView:
    return BookingView(
        id=b.id,
        tenant_id=b.tenant_id,
        lead_id=b.lead_id,
        contact_id=b.contact_id,
        provider=b.provider,
        provider_booking_id=b.provider_booking_id,
        provider_booking_uid=b.provider_booking_uid,
        status=b.status,
        start_at=b.start_at,
        end_at=b.end_at,
        timezone=b.timezone,
        duration_minutes=b.duration_minutes,
        meeting_url=b.meeting_url,
        attendee_name=b.attendee_name,
        attendee_email=b.attendee_email,
        attendee_phone=b.attendee_phone,
        host_name=b.host_name,
        title=b.title,
        calendar_mode=b.calendar_mode,
        created_at=b.created_at,
        notification_custom=_notification_custom(b.metadata_json),
    )


def serialize_resource(r: TenantSchedulingResource) -> dict[str, Any]:
    return {
        "id": r.id,
        "tenant_id": r.tenant_id,
        "name": r.name,
        "resource_type": r.resource_type,
        "team": r.team,
        "email": r.email,
        "phone": r.phone,
        "priority": r.priority,
        "is_active": r.is_active,
        "timezone": r.timezone,
        "capacity": r.capacity,
        "working_hours": r.working_hours_json,
        "total_assigned_count": r.total_assigned_count,
        "last_assigned_at": r.last_assigned_at,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
        "calendars": [
            {
                "id": rc.id,
                "resource_id": rc.resource_id,
                "calendar_id": rc.calendar_id,
                "is_blocking": rc.is_blocking,
                "is_destination": rc.is_destination,
                "created_at": rc.created_at,
                "google_calendar_id": rc.calendar.google_calendar_id if rc.calendar else None,
                "summary": rc.calendar.summary if rc.calendar else None,
            }
            for rc in (r.resource_calendars or [])
        ],
    }


def serialize_team(t: TenantSchedulingTeam) -> dict[str, Any]:
    return {
        "id": t.id,
        "tenant_id": t.tenant_id,
        "name": t.name,
        "description": t.description,
        "routing_strategy": t.routing_strategy,
        "is_active": t.is_active,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
        "members": [
            {
                "id": m.id,
                "team_id": m.team_id,
                "resource_id": m.resource_id,
                "priority": m.priority,
                "is_active": m.is_active,
                "created_at": m.created_at,
                "resource_name": m.resource.name if m.resource else None,
                "resource_email": m.resource.email if m.resource else None,
            }
            for m in (t.members or [])
        ],
    }


def serialize_exception(exc: TenantSchedulingAvailabilityException) -> dict[str, Any]:
    return {
        "id": exc.id,
        "tenant_id": exc.tenant_id,
        "resource_id": exc.resource_id,
        "exception_date": exc.exception_date,
        "exception_type": exc.exception_type,
        "start_time": exc.start_time,
        "end_time": exc.end_time,
        "reason": exc.reason,
        "created_at": exc.created_at,
        "updated_at": exc.updated_at,
        "resource_name": exc.resource.name if exc.resource else None,
    }


def serialize_agent_config(cfg: TenantAgentSchedulingConfig) -> dict[str, Any]:
    return {
        "id": cfg.id,
        "tenant_id": cfg.tenant_id,
        "agent_id": cfg.agent_id,
        "provider": cfg.provider,
        "scheduling_config_id": cfg.scheduling_config_id,
        "event_type_id": cfg.event_type_id,
        "resource_id": cfg.resource_id,
        "team_id": cfg.team_id,
        "routing_strategy": cfg.routing_strategy,
        "duration_minutes": cfg.duration_minutes,
        "allow_check_availability": cfg.allow_check_availability,
        "allow_create_booking": cfg.allow_create_booking,
        "allow_reschedule": cfg.allow_reschedule,
        "allow_cancel": cfg.allow_cancel,
        "is_active": cfg.is_active,
        "created_at": cfg.created_at,
        "updated_at": cfg.updated_at,
        "resource_name": cfg.resource.name if cfg.resource else None,
        "team_name": cfg.team.name if cfg.team else None,
        "event_type_name": cfg.event_type.name if cfg.event_type else None,
    }


def list_local_schedules(db: Session, tenant_id: str, provider: str | None) -> list[dict[str, Any]]:
    stmt = select(TenantSchedulingSchedule).where(
        TenantSchedulingSchedule.tenant_id == tenant_id,
        TenantSchedulingSchedule.sync_status != "remote_deleted",
    )
    if provider:
        stmt = stmt.where(TenantSchedulingSchedule.provider == provider)
    return [
        {
            "id": s.id,
            "tenant_id": s.tenant_id,
            "provider": s.provider,
            "name": s.name,
            "timezone": s.timezone,
            "working_hours": s.working_hours_json,
            "overrides": s.overrides_json,
            "provider_schedule_id": s.provider_schedule_id,
            "is_default": s.is_default,
            "is_active": s.is_active,
            "sync_status": s.sync_status,
            "last_synced_at": s.last_synced_at,
        }
        for s in db.scalars(stmt)
    ]


def list_local_event_types(db: Session, tenant_id: str, provider: str | None) -> list[dict[str, Any]]:
    stmt = select(TenantSchedulingEventType).where(
        TenantSchedulingEventType.tenant_id == tenant_id,
        TenantSchedulingEventType.sync_status != "remote_deleted",
    )
    if provider:
        stmt = stmt.where(TenantSchedulingEventType.provider == provider)
    return [
        {
            "id": et.id,
            "tenant_id": et.tenant_id,
            "provider": et.provider,
            "name": et.name,
            "slug": et.slug,
            "description": et.description,
            "duration_minutes": et.duration_minutes,
            "slot_interval_minutes": et.slot_interval_minutes,
            "buffer_before_minutes": et.buffer_before_minutes,
            "buffer_after_minutes": et.buffer_after_minutes,
            "minimum_notice_minutes": et.minimum_notice_minutes,
            "timezone": et.timezone,
            "local_schedule_id": et.local_schedule_id,
            "local_team_id": et.local_team_id,
            "provider_event_type_id": et.provider_event_type_id,
            "provider_event_type_slug": et.provider_event_type_slug,
            "is_active": et.is_active,
            "sync_status": et.sync_status,
            "last_synced_at": et.last_synced_at,
        }
        for et in db.scalars(stmt)
    ]
