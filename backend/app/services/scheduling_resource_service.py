from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.integrations import (
    TenantAgentSchedulingConfig,
    TenantGoogleCalendar,
    TenantGoogleCalendarConnection,
    TenantSchedulingAvailabilityException,
    TenantSchedulingConfig,
    TenantSchedulingResource,
    TenantSchedulingResourceCalendar,
    TenantSchedulingTeam,
    TenantSchedulingTeamMember,
)
from app.services.google_calendar_service import GoogleCalendarService

logger = logging.getLogger(__name__)


class SchedulingResourceService:
    def __init__(self, db: Session, google_service: GoogleCalendarService | None = None) -> None:
        self.db = db
        self.google_service = google_service or GoogleCalendarService(db)

    # -------------------------------------------------------------------------
    # Recursos
    # -------------------------------------------------------------------------
    def create_resource(
        self,
        *,
        tenant_id: str,
        name: str,
        resource_type: str = "user",
        team: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        priority: int = 1,
        timezone: str = "America/Bogota",
        capacity: int = 1,
        working_hours_json: dict | None = None,
    ) -> TenantSchedulingResource:
        resource = TenantSchedulingResource(
            tenant_id=tenant_id,
            name=name,
            resource_type=resource_type,
            team=team,
            email=email,
            phone=phone,
            priority=priority,
            timezone=timezone,
            capacity=capacity,
            working_hours_json=working_hours_json,
        )
        self.db.add(resource)
        self.db.commit()
        self.db.refresh(resource)
        return resource

    def get_resource(self, tenant_id: str, resource_id: str) -> TenantSchedulingResource | None:
        stmt = (
            select(TenantSchedulingResource)
            .options(joinedload(TenantSchedulingResource.resource_calendars).joinedload(TenantSchedulingResourceCalendar.calendar))
            .where(
                TenantSchedulingResource.tenant_id == tenant_id,
                TenantSchedulingResource.id == resource_id,
            )
        )
        return self.db.scalar(stmt)

    def list_resources(self, tenant_id: str, team: str | None = None) -> list[TenantSchedulingResource]:
        stmt = (
            select(TenantSchedulingResource)
            .options(joinedload(TenantSchedulingResource.resource_calendars).joinedload(TenantSchedulingResourceCalendar.calendar))
            .where(TenantSchedulingResource.tenant_id == tenant_id)
        )
        if team:
            stmt = stmt.where(TenantSchedulingResource.team == team)
        return list(self.db.scalars(stmt.order_by(TenantSchedulingResource.priority.desc(), TenantSchedulingResource.created_at.asc())).unique().all())

    def update_resource(
        self,
        tenant_id: str,
        resource_id: str,
        payload: dict[str, Any],
    ) -> TenantSchedulingResource:
        resource = self.get_resource(tenant_id, resource_id)
        if not resource:
            raise ValueError("Scheduling resource not found.")
        for key, val in payload.items():
            if val is not None and hasattr(resource, key):
                setattr(resource, key, val)
        self.db.commit()
        self.db.refresh(resource)
        return resource

    def update_resource_availability(
        self,
        tenant_id: str,
        resource_id: str,
        working_hours_json: dict[str, Any],
    ) -> TenantSchedulingResource:
        resource = self.get_resource(tenant_id, resource_id)
        if not resource:
            raise ValueError("Scheduling resource not found.")
        resource.working_hours_json = working_hours_json
        self.db.commit()
        self.db.refresh(resource)
        return resource

    def delete_resource(self, tenant_id: str, resource_id: str) -> None:
        resource = self.get_resource(tenant_id, resource_id)
        if not resource:
            raise ValueError("Scheduling resource not found.")
        self.db.delete(resource)
        self.db.commit()

    # -------------------------------------------------------------------------
    # Calendarios del Recurso
    # -------------------------------------------------------------------------
    def assign_calendar_to_resource(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        calendar_id: str,
        is_blocking: bool = True,
        is_destination: bool = True,
    ) -> TenantSchedulingResourceCalendar:
        resource = self.get_resource(tenant_id, resource_id)
        if not resource:
            raise ValueError("Scheduling resource not found.")
        cal = self.db.get(TenantGoogleCalendar, calendar_id)
        if not cal or cal.tenant_id != tenant_id:
            raise ValueError("Google calendar not found.")

        # If setting is_destination=True, unset other destination calendars for this resource
        if is_destination:
            existing_dests = list(
                self.db.scalars(
                    select(TenantSchedulingResourceCalendar).where(
                        TenantSchedulingResourceCalendar.tenant_id == tenant_id,
                        TenantSchedulingResourceCalendar.resource_id == resource_id,
                        TenantSchedulingResourceCalendar.is_destination == True,  # noqa: E712
                    )
                ).all()
            )
            for d in existing_dests:
                if d.calendar_id != calendar_id:
                    d.is_destination = False

        mapping = self.db.scalar(
            select(TenantSchedulingResourceCalendar).where(
                TenantSchedulingResourceCalendar.tenant_id == tenant_id,
                TenantSchedulingResourceCalendar.resource_id == resource_id,
                TenantSchedulingResourceCalendar.calendar_id == calendar_id,
            )
        )
        if mapping is None:
            mapping = TenantSchedulingResourceCalendar(
                tenant_id=tenant_id,
                resource_id=resource_id,
                calendar_id=calendar_id,
                is_blocking=is_blocking,
                is_destination=is_destination,
            )
            self.db.add(mapping)
        else:
            mapping.is_blocking = is_blocking
            mapping.is_destination = is_destination

        self.db.commit()
        self.db.refresh(mapping)
        return mapping

    # -------------------------------------------------------------------------
    # Equipos de Scheduling
    # -------------------------------------------------------------------------
    def create_team(
        self,
        *,
        tenant_id: str,
        name: str,
        description: str | None = None,
        routing_strategy: str = "round_robin",
        is_active: bool = True,
    ) -> TenantSchedulingTeam:
        team = TenantSchedulingTeam(
            tenant_id=tenant_id,
            name=name,
            description=description,
            routing_strategy=routing_strategy,
            is_active=is_active,
        )
        self.db.add(team)
        self.db.commit()
        self.db.refresh(team)
        return team

    def get_team(self, tenant_id: str, team_id: str) -> TenantSchedulingTeam | None:
        stmt = (
            select(TenantSchedulingTeam)
            .options(joinedload(TenantSchedulingTeam.members).joinedload(TenantSchedulingTeamMember.resource))
            .where(
                TenantSchedulingTeam.tenant_id == tenant_id,
                TenantSchedulingTeam.id == team_id,
            )
        )
        return self.db.scalar(stmt)

    def list_teams(self, tenant_id: str) -> list[TenantSchedulingTeam]:
        stmt = (
            select(TenantSchedulingTeam)
            .options(joinedload(TenantSchedulingTeam.members).joinedload(TenantSchedulingTeamMember.resource))
            .where(TenantSchedulingTeam.tenant_id == tenant_id)
            .order_by(TenantSchedulingTeam.name.asc())
        )
        return list(self.db.scalars(stmt).unique().all())

    def update_team(
        self,
        tenant_id: str,
        team_id: str,
        payload: dict[str, Any],
    ) -> TenantSchedulingTeam:
        team = self.get_team(tenant_id, team_id)
        if not team:
            raise ValueError("Scheduling team not found.")
        for key, val in payload.items():
            if val is not None and hasattr(team, key):
                setattr(team, key, val)
        self.db.commit()
        self.db.refresh(team)
        return team

    def delete_team(self, tenant_id: str, team_id: str) -> None:
        team = self.get_team(tenant_id, team_id)
        if not team:
            raise ValueError("Scheduling team not found.")
        self.db.delete(team)
        self.db.commit()

    def add_team_member(
        self,
        *,
        tenant_id: str,
        team_id: str,
        resource_id: str,
        priority: int = 1,
        is_active: bool = True,
    ) -> TenantSchedulingTeamMember:
        team = self.get_team(tenant_id, team_id)
        if not team:
            raise ValueError("Scheduling team not found.")
        resource = self.get_resource(tenant_id, resource_id)
        if not resource:
            raise ValueError("Scheduling resource not found.")

        member = self.db.scalar(
            select(TenantSchedulingTeamMember).where(
                TenantSchedulingTeamMember.tenant_id == tenant_id,
                TenantSchedulingTeamMember.team_id == team_id,
                TenantSchedulingTeamMember.resource_id == resource_id,
            )
        )
        if not member:
            member = TenantSchedulingTeamMember(
                tenant_id=tenant_id,
                team_id=team_id,
                resource_id=resource_id,
                priority=priority,
                is_active=is_active,
            )
            self.db.add(member)
        else:
            member.priority = priority
            member.is_active = is_active
        self.db.commit()
        self.db.refresh(member)
        return member

    def remove_team_member(self, tenant_id: str, team_id: str, resource_id: str) -> None:
        member = self.db.scalar(
            select(TenantSchedulingTeamMember).where(
                TenantSchedulingTeamMember.tenant_id == tenant_id,
                TenantSchedulingTeamMember.team_id == team_id,
                TenantSchedulingTeamMember.resource_id == resource_id,
            )
        )
        if not member:
            raise ValueError("Team member not found.")
        self.db.delete(member)
        self.db.commit()

    # -------------------------------------------------------------------------
    # Excepciones de Disponibilidad
    # -------------------------------------------------------------------------
    def create_exception(
        self,
        *,
        tenant_id: str,
        exception_date: date,
        exception_type: str = "unavailable",
        resource_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        reason: str | None = None,
    ) -> TenantSchedulingAvailabilityException:
        if resource_id:
            res = self.get_resource(tenant_id, resource_id)
            if not res:
                raise ValueError("Resource not found.")

        exc = TenantSchedulingAvailabilityException(
            tenant_id=tenant_id,
            resource_id=resource_id,
            exception_date=exception_date,
            exception_type=exception_type,
            start_time=start_time,
            end_time=end_time,
            reason=reason,
        )
        self.db.add(exc)
        self.db.commit()
        self.db.refresh(exc)
        return exc

    def list_exceptions(self, tenant_id: str, resource_id: str | None = None) -> list[TenantSchedulingAvailabilityException]:
        stmt = (
            select(TenantSchedulingAvailabilityException)
            .options(joinedload(TenantSchedulingAvailabilityException.resource))
            .where(TenantSchedulingAvailabilityException.tenant_id == tenant_id)
        )
        if resource_id:
            stmt = stmt.where(TenantSchedulingAvailabilityException.resource_id == resource_id)
        return list(self.db.scalars(stmt.order_by(TenantSchedulingAvailabilityException.exception_date.asc())).unique().all())

    def delete_exception(self, tenant_id: str, exception_id: str) -> None:
        exc = self.db.scalar(
            select(TenantSchedulingAvailabilityException).where(
                TenantSchedulingAvailabilityException.tenant_id == tenant_id,
                TenantSchedulingAvailabilityException.id == exception_id,
            )
        )
        if not exc:
            raise ValueError("Availability exception not found.")
        self.db.delete(exc)
        self.db.commit()

    # -------------------------------------------------------------------------
    # Asignación a Agentes
    # -------------------------------------------------------------------------
    def get_agent_config(self, tenant_id: str, agent_id: str) -> TenantAgentSchedulingConfig | None:
        stmt = (
            select(TenantAgentSchedulingConfig)
            .options(
                joinedload(TenantAgentSchedulingConfig.resource),
                joinedload(TenantAgentSchedulingConfig.team),
                joinedload(TenantAgentSchedulingConfig.scheduling_config),
            )
            .where(
                TenantAgentSchedulingConfig.tenant_id == tenant_id,
                TenantAgentSchedulingConfig.agent_id == agent_id,
            )
        )
        return self.db.scalar(stmt)

    def upsert_agent_config(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        payload: dict[str, Any],
    ) -> TenantAgentSchedulingConfig:
        config = self.get_agent_config(tenant_id, agent_id)
        if not config:
            config = TenantAgentSchedulingConfig(
                tenant_id=tenant_id,
                agent_id=agent_id,
                **payload,
            )
            self.db.add(config)
        else:
            for key, val in payload.items():
                if val is not None and hasattr(config, key):
                    setattr(config, key, val)
        self.db.commit()
        self.db.refresh(config)
        return config

    # -------------------------------------------------------------------------
    # Selección de Recurso (Single & Round Robin Estricto)
    # -------------------------------------------------------------------------
    def select_resource_round_robin(
        self,
        *,
        tenant_id: str,
        team_id: str | None = None,
        team_name: str | None = None,
        slot_start: datetime | None = None,
        duration_minutes: int = 30,
        buffer_before_minutes: int = 0,
        buffer_after_minutes: int = 0,
    ) -> tuple[TenantSchedulingResource, str | None] | tuple[None, None]:
        """
        Selecciona un recurso bajo estrategia Round Robin.
        IMPORTANTE: NUNCA retorna un recurso ocupado ni hace fallback a uno ocupado.
        Si ninguno está disponible, retorna (None, None).
        """
        # 1. Fetch team members if team_id or team_name is given
        candidate_ids: list[str] = []
        if team_id:
            members = list(
                self.db.scalars(
                    select(TenantSchedulingTeamMember.resource_id).where(
                        TenantSchedulingTeamMember.tenant_id == tenant_id,
                        TenantSchedulingTeamMember.team_id == team_id,
                        TenantSchedulingTeamMember.is_active == True,  # noqa: E712
                    ).order_by(TenantSchedulingTeamMember.priority.desc())
                ).all()
            )
            candidate_ids = members
        elif team_name:
            team = self.db.scalar(
                select(TenantSchedulingTeam).where(
                    TenantSchedulingTeam.tenant_id == tenant_id,
                    TenantSchedulingTeam.name == team_name,
                    TenantSchedulingTeam.is_active == True,  # noqa: E712
                )
            )
            if team:
                members = list(
                    self.db.scalars(
                        select(TenantSchedulingTeamMember.resource_id).where(
                            TenantSchedulingTeamMember.tenant_id == tenant_id,
                            TenantSchedulingTeamMember.team_id == team.id,
                            TenantSchedulingTeamMember.is_active == True,  # noqa: E712
                        ).order_by(TenantSchedulingTeamMember.priority.desc())
                    ).all()
                )
                candidate_ids = members

        stmt = (
            select(TenantSchedulingResource)
            .options(joinedload(TenantSchedulingResource.resource_calendars).joinedload(TenantSchedulingResourceCalendar.calendar))
            .where(
                TenantSchedulingResource.tenant_id == tenant_id,
                TenantSchedulingResource.is_active == True,  # noqa: E712
            )
        )
        if candidate_ids:
            stmt = stmt.where(TenantSchedulingResource.id.in_(candidate_ids))
        elif team_name:
            # Fallback backward-compatible: match string team column
            stmt = stmt.where(TenantSchedulingResource.team == team_name)

        # Order by priority, least recently assigned first, lowest count, then created_at
        candidates = list(
            self.db.scalars(
                stmt.order_by(
                    TenantSchedulingResource.priority.desc(),
                    TenantSchedulingResource.last_assigned_at.asc().nullsfirst(),
                    TenantSchedulingResource.total_assigned_count.asc(),
                    TenantSchedulingResource.created_at.asc(),
                    TenantSchedulingResource.id.asc(),
                )
            ).unique().all()
        )

        if not candidates:
            return None, None

        chosen_resource: TenantSchedulingResource | None = None
        chosen_calendar_id: str | None = None

        for resource in candidates:
            destination_cal = next(
                (rc.calendar.google_calendar_id for rc in resource.resource_calendars if rc.is_destination and rc.calendar),
                None,
            )

            # Check working hours of resource if slot_start is given
            if slot_start and resource.working_hours_json:
                day_name = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][slot_start.weekday()]
                day_ranges = resource.working_hours_json.get(day_name, [])
                if not day_ranges:
                    continue  # Day off for this resource

                # Check if slot falls in any configured range
                slot_time_str = slot_start.strftime("%H:%M")
                slot_end_time = (slot_start + timedelta(minutes=duration_minutes)).strftime("%H:%M")
                in_hours = False
                for r in day_ranges:
                    start_r = r.get("start") if isinstance(r, dict) else r[0]
                    end_r = r.get("end") if isinstance(r, dict) else r[1]
                    if start_r <= slot_time_str and slot_end_time <= end_r:
                        in_hours = True
                        break
                if not in_hours:
                    continue  # Out of working hours

            # Check exceptions for resource
            if slot_start:
                slot_date = slot_start.date()
                exc = self.db.scalar(
                    select(TenantSchedulingAvailabilityException).where(
                        TenantSchedulingAvailabilityException.tenant_id == tenant_id,
                        (TenantSchedulingAvailabilityException.resource_id == resource.id) | (TenantSchedulingAvailabilityException.resource_id.is_(None)),
                        TenantSchedulingAvailabilityException.exception_date == slot_date,
                    )
                )
                if exc:
                    if exc.exception_type == "unavailable":
                        continue
                    if exc.exception_type == "custom_hours" and exc.start_time and exc.end_time:
                        slot_time_str = slot_start.strftime("%H:%M")
                        slot_end_time = (slot_start + timedelta(minutes=duration_minutes)).strftime("%H:%M")
                        if not (exc.start_time <= slot_time_str and slot_end_time <= exc.end_time):
                            continue

            # Check FreeBusy collision
            if slot_start and resource.resource_calendars:
                blocking_cals = [rc.calendar.google_calendar_id for rc in resource.resource_calendars if rc.is_blocking and rc.calendar]
                if blocking_cals:
                    slot_window_start = slot_start - timedelta(minutes=buffer_before_minutes)
                    slot_window_end = slot_start + timedelta(minutes=duration_minutes + buffer_after_minutes)

                    conn = self.db.scalar(
                        select(TenantGoogleCalendarConnection).where(
                            TenantGoogleCalendarConnection.tenant_id == tenant_id,
                            TenantGoogleCalendarConnection.status == "connected",
                        )
                    )
                    if conn:
                        try:
                            busy = self.google_service.get_freebusy_intervals(
                                connection=conn,
                                calendar_ids=blocking_cals,
                                time_min=slot_window_start,
                                time_max=slot_window_end,
                            )
                            if busy:
                                continue  # Busy collision, test next candidate
                        except Exception as exc:
                            logger.warning("Error checking freebusy for resource %s: %s", resource.name, exc)

            # If all checks pass, we select this resource
            chosen_resource = resource
            chosen_calendar_id = destination_cal
            break

        # STRICT: If no resource is free, return None (NO fallback to a busy resource)
        if not chosen_resource:
            return None, None

        # Update assignment counters
        chosen_resource.last_assigned_at = datetime.now(UTC)
        chosen_resource.total_assigned_count += 1
        self.db.commit()
        self.db.refresh(chosen_resource)

        return chosen_resource, chosen_calendar_id
