from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.integrations import (
    TenantGoogleCalendar,
    TenantGoogleCalendarConnection,
    TenantSchedulingResource,
    TenantSchedulingResourceCalendar,
)
from app.services.google_calendar_service import GoogleCalendarService

logger = logging.getLogger(__name__)


class SchedulingResourceService:
    def __init__(self, db: Session, google_service: GoogleCalendarService | None = None) -> None:
        self.db = db
        self.google_service = google_service or GoogleCalendarService(db)

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

    def list_resources(self, tenant_id: str, team: str | None = None) -> list[TenantSchedulingResource]:
        stmt = (
            select(TenantSchedulingResource)
            .options(joinedload(TenantSchedulingResource.resource_calendars).joinedload(TenantSchedulingResourceCalendar.calendar))
            .where(TenantSchedulingResource.tenant_id == tenant_id)
        )
        if team:
            stmt = stmt.where(TenantSchedulingResource.team == team)
        return list(self.db.scalars(stmt.order_by(TenantSchedulingResource.priority.desc(), TenantSchedulingResource.created_at.asc())).unique().all())

    def assign_calendar_to_resource(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        calendar_id: str,
        is_blocking: bool = True,
        is_destination: bool = True,
    ) -> TenantSchedulingResourceCalendar:
        resource = self.db.get(TenantSchedulingResource, resource_id)
        if not resource or resource.tenant_id != tenant_id:
            raise ValueError("Scheduling resource not found.")
        cal = self.db.get(TenantGoogleCalendar, calendar_id)
        if not cal or cal.tenant_id != tenant_id:
            raise ValueError("Google calendar not found.")

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

    def select_resource_round_robin(
        self,
        *,
        tenant_id: str,
        team: str | None = None,
        slot_start: datetime | None = None,
        duration_minutes: int = 30,
    ) -> tuple[TenantSchedulingResource, str | None] | tuple[None, None]:
        stmt = (
            select(TenantSchedulingResource)
            .options(joinedload(TenantSchedulingResource.resource_calendars).joinedload(TenantSchedulingResourceCalendar.calendar))
            .where(
                TenantSchedulingResource.tenant_id == tenant_id,
                TenantSchedulingResource.is_active == True,  # noqa: E712
            )
        )
        if team:
            stmt = stmt.where(TenantSchedulingResource.team == team)

        # Order by least recently assigned first, then lowest count
        candidates = list(
            self.db.scalars(
                stmt.order_by(
                    TenantSchedulingResource.last_assigned_at.asc().nullsfirst(),
                    TenantSchedulingResource.total_assigned_count.asc(),
                )
            ).unique().all()
        )

        if not candidates:
            return None, None

        # Check availability for candidate if slot_start is provided
        chosen_resource: TenantSchedulingResource | None = None
        chosen_calendar_id: str | None = None

        for resource in candidates:
            destination_cal = next(
                (rc.calendar.google_calendar_id for rc in resource.resource_calendars if rc.is_destination and rc.calendar),
                None,
            )
            if slot_start and resource.resource_calendars:
                # check if blocking calendars are free
                blocking_cals = [rc.calendar.google_calendar_id for rc in resource.resource_calendars if rc.is_blocking and rc.calendar]
                if blocking_cals:
                    slot_end = slot_start + timedelta(minutes=duration_minutes)
                    # Resolve connection for calendar
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
                                time_min=slot_start,
                                time_max=slot_end,
                            )
                            if busy:
                                continue  # This resource has a conflict, try next
                        except Exception as exc:
                            logger.warning("Error checking freebusy for resource %s: %s", resource.name, exc)

            chosen_resource = resource
            chosen_calendar_id = destination_cal
            break

        if not chosen_resource:
            chosen_resource = candidates[0]
            chosen_calendar_id = next(
                (rc.calendar.google_calendar_id for rc in chosen_resource.resource_calendars if rc.is_destination and rc.calendar),
                None,
            )

        # Update assignment counters
        chosen_resource.last_assigned_at = datetime.now(UTC)
        chosen_resource.total_assigned_count += 1
        self.db.commit()
        self.db.refresh(chosen_resource)

        return chosen_resource, chosen_calendar_id
