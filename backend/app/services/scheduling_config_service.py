from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integrations import (
    TenantAgentSchedulingConfig,
    TenantGoogleCalendar,
    TenantGoogleCalendarConnection,
    TenantSchedulingAvailabilityException,
    TenantSchedulingConfig,
    TenantSchedulingResource,
    TenantSchedulingTeam,
    TenantSchedulingTeamMember,
)
from app.models.crm import CrmBooking

logger = logging.getLogger(__name__)


class SchedulingConfigService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_or_create_config(self, tenant_id: str) -> TenantSchedulingConfig:
        config = self.db.scalar(
            select(TenantSchedulingConfig).where(TenantSchedulingConfig.tenant_id == tenant_id)
        )
        if not config:
            config = TenantSchedulingConfig(
                tenant_id=tenant_id,
                timezone="America/Bogota",
                default_duration_minutes=30,
                slot_interval_minutes=30,
                buffer_before_minutes=0,
                buffer_after_minutes=0,
                minimum_notice_minutes=60,
                maximum_booking_days=30,
                routing_strategy="single",
                is_active=True,
            )
            self.db.add(config)
            self.db.commit()
            self.db.refresh(config)
        return config

    def update_config(self, tenant_id: str, payload: dict[str, Any]) -> TenantSchedulingConfig:
        config = self.get_or_create_config(tenant_id)
        for key, val in payload.items():
            if val is not None and hasattr(config, key):
                setattr(config, key, val)
        self.db.commit()
        self.db.refresh(config)
        return config

    def get_dashboard_summary(self, tenant_id: str) -> dict[str, Any]:
        config = self.get_or_create_config(tenant_id)
        active_resources = list(
            self.db.scalars(
                select(TenantSchedulingResource).where(
                    TenantSchedulingResource.tenant_id == tenant_id,
                    TenantSchedulingResource.is_active == True,  # noqa: E712
                )
            ).all()
        )
        teams = list(
            self.db.scalars(
                select(TenantSchedulingTeam).where(
                    TenantSchedulingTeam.tenant_id == tenant_id,
                    TenantSchedulingTeam.is_active == True,  # noqa: E712
                )
            ).all()
        )
        calendars = list(
            self.db.scalars(
                select(TenantGoogleCalendar).where(
                    TenantGoogleCalendar.tenant_id == tenant_id,
                )
            ).all()
        )
        active_conn = self.db.scalar(
            select(TenantGoogleCalendarConnection).where(
                TenantGoogleCalendarConnection.tenant_id == tenant_id,
                TenantGoogleCalendarConnection.status == "connected",
            )
        )
        agent_configs = list(
            self.db.scalars(
                select(TenantAgentSchedulingConfig).where(
                    TenantAgentSchedulingConfig.tenant_id == tenant_id,
                    TenantAgentSchedulingConfig.is_active == True,  # noqa: E712
                )
            ).all()
        )

        from datetime import UTC, datetime
        upcoming_count = self.db.scalar(
            select(sa_func.count()).select_from(CrmBooking).where(
                CrmBooking.tenant_id == tenant_id,
                CrmBooking.status.in_(["scheduled", "accepted", "confirmed"]),
                CrmBooking.start_at >= datetime.now(UTC),
            )
        ) or 0

        # Build alerts
        alerts: list[str] = []
        has_destination = any(c.is_booking_destination for c in calendars)
        if not active_conn:
            alerts.append("Google Calendar no está conectado.")
        elif not has_destination:
            alerts.append("No hay ningún calendario configurado como destino de reservas.")

        resources_without_hours = [r.name for r in active_resources if not r.working_hours_json]
        if resources_without_hours:
            alerts.append(f"{len(resources_without_hours)} recurso(s) no tienen disponibilidad configurada: {', '.join(resources_without_hours[:3])}.")

        # Check teams without members
        for team in teams:
            member_count = self.db.scalar(
                select(sa_func.count()).select_from(TenantSchedulingTeamMember).where(
                    TenantSchedulingTeamMember.team_id == team.id,
                    TenantSchedulingTeamMember.is_active == True,  # noqa: E712
                )
            ) or 0
            if member_count == 0:
                alerts.append(f"El equipo '{team.name}' no tiene miembros asignados.")

        return {
            "active_resources_count": len(active_resources),
            "teams_count": len(teams),
            "connected_calendars_count": len(calendars),
            "upcoming_bookings_count": upcoming_count,
            "google_connected": bool(active_conn),
            "availability_configured": any(bool(r.working_hours_json) for r in active_resources),
            "agents_count": len(agent_configs),
            "alerts": alerts,
        }


from sqlalchemy import func as sa_func
