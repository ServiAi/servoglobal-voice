from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integrations import (
    TenantGoogleCalendarConnection,
    TenantSchedulingConfig,
    TenantSchedulingEventType,
)
from app.services.google_calendar_service import GoogleCalendarService
from app.services.scheduling_config_service import SchedulingConfigService
from app.services.scheduling_protocols import SchedulingAdminProvider, SchedulingProviderCapabilities
from app.services.scheduling_resource_service import SchedulingResourceService

logger = logging.getLogger(__name__)


class GoogleSchedulingAdminProvider(SchedulingAdminProvider):
    """Google Calendar admin provider where ServiGlobal is the scheduling engine."""

    def __init__(self, db: Session, tenant_id: str) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.config_service = SchedulingConfigService(db)
        self.resource_service = SchedulingResourceService(db)
        self.google_service = GoogleCalendarService(db)

    def capabilities(self) -> SchedulingProviderCapabilities:
        return SchedulingProviderCapabilities(
            schedules=True,
            native_schedules=False,
            event_types=True,
            native_event_types=False,
            resources=True,
            teams=True,
            native_round_robin=False,
            exceptions=True,
            native_exceptions=False,
            external_calendars=True,
            booking=True,
            reschedule=True,
            cancel=True,
        )

    def discover(self) -> dict[str, Any]:
        conn = self.db.scalar(
            select(TenantGoogleCalendarConnection).where(
                TenantGoogleCalendarConnection.tenant_id == self.tenant_id,
                TenantGoogleCalendarConnection.status == "connected",
            ).order_by(TenantGoogleCalendarConnection.created_at.desc())
        )
        return {
            "connected": conn is not None,
            "account_email": conn.google_account_email if conn else None,
            "calendar_id": conn.calendar_id if conn else None,
            "calendars_count": len(conn.calendars) if conn and conn.calendars else 0,
        }

    def list_schedules(self) -> list[dict[str, Any]]:
        cfg = self.config_service.get_or_create_config(self.tenant_id)
        return [
            {
                "id": f"serviglobal-{self.tenant_id}",
                "name": "Horario principal ServiGlobal",
                "timeZone": cfg.timezone,
                "isDefault": True,
                "availability": cfg.working_hours_json or {},
            }
        ]

    def get_schedule(self, schedule_id: str) -> dict[str, Any]:
        schedules = self.list_schedules()
        return schedules[0] if schedules else {}

    def create_schedule(self, payload: dict[str, Any]) -> dict[str, Any]:
        working_hours = payload.get("availability") or payload.get("working_hours_json") or {}
        cfg = self.config_service.update_config(self.tenant_id, {"working_hours_json": working_hours})
        return {
            "id": f"serviglobal-{self.tenant_id}",
            "name": payload.get("name", "Horario principal ServiGlobal"),
            "timeZone": cfg.timezone,
            "isDefault": True,
            "availability": cfg.working_hours_json or {},
        }

    def update_schedule(self, schedule_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        working_hours = payload.get("availability") or payload.get("working_hours_json") or {}
        cfg = self.config_service.update_config(self.tenant_id, {"working_hours_json": working_hours})
        return {
            "id": f"serviglobal-{self.tenant_id}",
            "name": payload.get("name", "Horario principal ServiGlobal"),
            "timeZone": cfg.timezone,
            "isDefault": True,
            "availability": cfg.working_hours_json or {},
        }

    def delete_schedule(self, schedule_id: str) -> bool:
        self.config_service.update_config(self.tenant_id, {"working_hours_json": {}})
        return True

    def list_event_types(self) -> list[dict[str, Any]]:
        event_types = list(
            self.db.scalars(
                select(TenantSchedulingEventType).where(
                    TenantSchedulingEventType.tenant_id == self.tenant_id,
                    TenantSchedulingEventType.provider == "google_calendar",
                    TenantSchedulingEventType.sync_status != "remote_deleted",
                )
            )
        )
        if not event_types:
            cfg = self.config_service.get_or_create_config(self.tenant_id)
            return [
                {
                    "id": f"default-{self.tenant_id}",
                    "name": "Cita Estándar ServiGlobal",
                    "slug": "cita-estandar",
                    "duration": cfg.default_duration_minutes,
                    "slotInterval": cfg.slot_interval_minutes,
                    "beforeEventBuffer": cfg.buffer_before_minutes,
                    "afterEventBuffer": cfg.buffer_after_minutes,
                    "minimumBookingNotice": cfg.minimum_notice_minutes,
                    "isActive": True,
                }
            ]
        return [
            {
                "id": et.id,
                "name": et.name,
                "slug": et.slug,
                "description": et.description,
                "duration": et.duration_minutes,
                "slotInterval": et.slot_interval_minutes,
                "beforeEventBuffer": et.buffer_before_minutes,
                "afterEventBuffer": et.buffer_after_minutes,
                "minimumBookingNotice": et.minimum_notice_minutes,
                "isActive": et.is_active,
            }
            for et in event_types
        ]

    def get_event_type(self, event_type_id: str) -> dict[str, Any]:
        et = self.db.scalar(
            select(TenantSchedulingEventType).where(
                TenantSchedulingEventType.tenant_id == self.tenant_id,
                TenantSchedulingEventType.id == event_type_id,
            )
        )
        if not et:
            return {}
        return {
            "id": et.id,
            "name": et.name,
            "slug": et.slug,
            "description": et.description,
            "duration": et.duration_minutes,
            "slotInterval": et.slot_interval_minutes,
            "beforeEventBuffer": et.buffer_before_minutes,
            "afterEventBuffer": et.buffer_after_minutes,
            "minimumBookingNotice": et.minimum_notice_minutes,
            "isActive": et.is_active,
        }

    def create_event_type(self, payload: dict[str, Any]) -> dict[str, Any]:
        cfg = self.config_service.get_or_create_config(self.tenant_id)
        et = TenantSchedulingEventType(
            tenant_id=self.tenant_id,
            provider="google_calendar",
            name=payload.get("name", "Nuevo tipo de cita"),
            slug=payload.get("slug", "cita"),
            description=payload.get("description"),
            duration_minutes=int(payload.get("duration", 30)),
            slot_interval_minutes=int(payload.get("slot_interval", payload.get("duration", 30))),
            buffer_before_minutes=int(payload.get("buffer_before", 0)),
            buffer_after_minutes=int(payload.get("buffer_after", 0)),
            minimum_notice_minutes=int(payload.get("minimum_notice", 60)),
            timezone=payload.get("timezone", cfg.timezone),
            is_active=bool(payload.get("is_active", True)),
            last_synced_at=datetime.now(UTC),
            sync_status="synced",
        )
        self.db.add(et)
        self.db.commit()
        self.db.refresh(et)
        return self.get_event_type(et.id)

    def update_event_type(self, event_type_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        et = self.db.scalar(
            select(TenantSchedulingEventType).where(
                TenantSchedulingEventType.tenant_id == self.tenant_id,
                TenantSchedulingEventType.id == event_type_id,
            )
        )
        if not et:
            raise ValueError(f"Event type {event_type_id} not found.")
        if "name" in payload:
            et.name = payload["name"]
        if "slug" in payload:
            et.slug = payload["slug"]
        if "description" in payload:
            et.description = payload["description"]
        if "duration" in payload:
            et.duration_minutes = int(payload["duration"])
        if "is_active" in payload:
            et.is_active = bool(payload["is_active"])
        et.last_synced_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(et)
        return self.get_event_type(et.id)

    def delete_event_type(self, event_type_id: str) -> bool:
        et = self.db.scalar(
            select(TenantSchedulingEventType).where(
                TenantSchedulingEventType.tenant_id == self.tenant_id,
                TenantSchedulingEventType.id == event_type_id,
            )
        )
        if et:
            et.sync_status = "remote_deleted"
            self.db.commit()
        return True

    def list_resources(self) -> list[dict[str, Any]]:
        resources = self.resource_service.list_resources(self.tenant_id)
        return [{"id": r.id, "name": r.name, "email": r.email, "is_active": r.is_active} for r in resources]

    def list_teams(self) -> list[dict[str, Any]]:
        teams = self.resource_service.list_teams(self.tenant_id)
        return [{"id": t.id, "name": t.name, "routing_strategy": t.routing_strategy, "is_active": t.is_active} for t in teams]

    def get_team(self, team_id: str) -> dict[str, Any]:
        t = self.resource_service.get_team(self.tenant_id, team_id)
        if not t:
            return {}
        return {"id": t.id, "name": t.name, "routing_strategy": t.routing_strategy, "is_active": t.is_active}

    def list_team_members(self, team_id: str) -> list[dict[str, Any]]:
        t = self.resource_service.get_team(self.tenant_id, team_id)
        if not t:
            return []
        return [
            {
                "id": m.id,
                "resource_id": m.resource_id,
                "priority": m.priority,
                "is_active": m.is_active,
                "resource_name": m.resource.name if m.resource else None,
            }
            for m in (t.members or [])
        ]

    def sync(self) -> dict[str, Any]:
        return {"status": "success", "provider": "google_calendar", "synced_at": datetime.now(UTC).isoformat()}
