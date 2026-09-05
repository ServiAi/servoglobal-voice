from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext, require_roles
from app.db.session import get_db
from app.models.integrations import (
    TenantAgentSchedulingConfig,
    TenantSchedulingAvailabilityException,
    TenantSchedulingEventType,
    TenantSchedulingResource,
    TenantSchedulingSchedule,
    TenantSchedulingTeam,
)
from app.schemas.scheduling import (
    AgentSchedulingConfigResponse,
    AgentSchedulingConfigUpsertRequest,
    CalComDiscoveryResponse,
    SchedulingAvailabilityExceptionCreateRequest,
    SchedulingAvailabilityExceptionResponse,
    SchedulingDashboardSummaryResponse,
    SchedulingEventTypeCreateRequest,
    SchedulingEventTypeResponse,
    SchedulingEventTypeUpdateRequest,
    SchedulingProviderCapabilitiesResponse,
    SchedulingResourceCalendarAssignRequest,
    SchedulingResourceCalendarResponse,
    SchedulingResourceCreateRequest,
    SchedulingResourceResponse,
    SchedulingResourceUpdateRequest,
    SchedulingScheduleCreateRequest,
    SchedulingScheduleResponse,
    SchedulingScheduleUpdateRequest,
    SchedulingTeamCreateRequest,
    SchedulingTeamMemberAddRequest,
    SchedulingTeamMemberResponse,
    SchedulingTeamResponse,
    SchedulingTeamUpdateRequest,
    TenantSchedulingConfigResponse,
    TenantSchedulingConfigUpdateRequest,
)
from app.core.scheduling_exceptions import SchedulingNotFoundError
from app.services.calcom_sync_service import CalComSyncService
from app.services.scheduling_availability_service import SchedulingAvailabilityService
from app.services.scheduling_config_service import SchedulingConfigService
from app.services.scheduling_provider_resolver import SchedulingProviderResolver
from app.services.scheduling_resource_service import SchedulingResourceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/scheduling", tags=["Scheduling"])

READ_ROLES = ["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"]
WRITE_ROLES = ["platform_admin", "tenant_admin"]


def _serialize_resource(r: TenantSchedulingResource) -> dict[str, Any]:
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


def _serialize_team(t: TenantSchedulingTeam) -> dict[str, Any]:
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


def _serialize_exception(exc: TenantSchedulingAvailabilityException) -> dict[str, Any]:
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


def _serialize_agent_config(cfg: TenantAgentSchedulingConfig) -> dict[str, Any]:
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


# -----------------------------------------------------------------------------
# Dashboard Summary & Config
# -----------------------------------------------------------------------------
@router.get("/dashboard/summary", response_model=SchedulingDashboardSummaryResponse)
def get_scheduling_dashboard_summary(
    auth: AuthContext = Depends(require_roles(READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = SchedulingConfigService(db)
    return service.get_dashboard_summary(auth.tenant_id)


@router.get("/config", response_model=TenantSchedulingConfigResponse)
def get_scheduling_config(
    auth: AuthContext = Depends(require_roles(READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = SchedulingConfigService(db)
    return service.get_or_create_config(auth.tenant_id)


@router.put("/config", response_model=TenantSchedulingConfigResponse)
def update_scheduling_config(
    payload: TenantSchedulingConfigUpdateRequest,
    auth: AuthContext = Depends(require_roles(WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = SchedulingConfigService(db)
    return service.update_config(auth.tenant_id, payload.model_dump(exclude_unset=True))


# -----------------------------------------------------------------------------
# Recursos (CRUD & Calendars)
# -----------------------------------------------------------------------------
@router.get("/resources", response_model=list[SchedulingResourceResponse])
def list_resources(
    team: Optional[str] = Query(None),
    auth: AuthContext = Depends(require_roles(READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = SchedulingResourceService(db)
    resources = service.list_resources(auth.tenant_id, team=team)
    return [_serialize_resource(r) for r in resources]


@router.post("/resources", response_model=SchedulingResourceResponse, status_code=status.HTTP_201_CREATED)
def create_resource(
    body: SchedulingResourceCreateRequest,
    auth: AuthContext = Depends(require_roles(WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = SchedulingResourceService(db)
    resource = service.create_resource(
        tenant_id=auth.tenant_id,
        name=body.name,
        resource_type=body.resource_type,
        team=body.team,
        email=body.email,
        phone=body.phone,
        priority=body.priority,
        timezone=body.timezone,
        capacity=body.capacity,
        working_hours_json=body.working_hours,
    )
    return _serialize_resource(resource)


@router.get("/resources/{resource_id}", response_model=SchedulingResourceResponse)
def get_resource(
    resource_id: str,
    auth: AuthContext = Depends(require_roles(READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = SchedulingResourceService(db)
    resource = service.get_resource(auth.tenant_id, resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found.")
    return _serialize_resource(resource)


@router.put("/resources/{resource_id}", response_model=SchedulingResourceResponse)
def update_resource(
    resource_id: str,
    body: SchedulingResourceUpdateRequest,
    auth: AuthContext = Depends(require_roles(WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = SchedulingResourceService(db)
    try:
        resource = service.update_resource(auth.tenant_id, resource_id, body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _serialize_resource(resource)


@router.delete("/resources/{resource_id}")
def delete_resource(
    resource_id: str,
    auth: AuthContext = Depends(require_roles(WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = SchedulingResourceService(db)
    try:
        service.delete_resource(auth.tenant_id, resource_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "deleted"}


@router.put("/resources/{resource_id}/availability", response_model=SchedulingResourceResponse)
def update_resource_availability(
    resource_id: str,
    working_hours: dict[str, Any],
    auth: AuthContext = Depends(require_roles(WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = SchedulingResourceService(db)
    try:
        resource = service.update_resource_availability(auth.tenant_id, resource_id, working_hours)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _serialize_resource(resource)


@router.post("/resources/{resource_id}/calendars", response_model=SchedulingResourceCalendarResponse)
def assign_calendar_to_resource(
    resource_id: str,
    body: SchedulingResourceCalendarAssignRequest,
    auth: AuthContext = Depends(require_roles(WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = SchedulingResourceService(db)
    try:
        mapping = service.assign_calendar_to_resource(
            tenant_id=auth.tenant_id,
            resource_id=resource_id,
            calendar_id=body.calendar_id,
            is_blocking=body.is_blocking,
            is_destination=body.is_destination,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "id": mapping.id,
        "resource_id": mapping.resource_id,
        "calendar_id": mapping.calendar_id,
        "is_blocking": mapping.is_blocking,
        "is_destination": mapping.is_destination,
        "created_at": mapping.created_at,
        "google_calendar_id": mapping.calendar.google_calendar_id if mapping.calendar else None,
        "summary": mapping.calendar.summary if mapping.calendar else None,
    }


# -----------------------------------------------------------------------------
# Equipos de Scheduling
# -----------------------------------------------------------------------------
@router.get("/teams", response_model=list[SchedulingTeamResponse])
def list_teams(
    auth: AuthContext = Depends(require_roles(READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = SchedulingResourceService(db)
    teams = service.list_teams(auth.tenant_id)
    return [_serialize_team(t) for t in teams]


@router.post("/teams", response_model=SchedulingTeamResponse, status_code=status.HTTP_201_CREATED)
def create_team(
    body: SchedulingTeamCreateRequest,
    auth: AuthContext = Depends(require_roles(WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = SchedulingResourceService(db)
    team = service.create_team(
        tenant_id=auth.tenant_id,
        name=body.name,
        description=body.description,
        routing_strategy=body.routing_strategy,
        is_active=body.is_active,
    )
    return _serialize_team(team)


@router.get("/teams/{team_id}", response_model=SchedulingTeamResponse)
def get_team(
    team_id: str,
    auth: AuthContext = Depends(require_roles(READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = SchedulingResourceService(db)
    team = service.get_team(auth.tenant_id, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found.")
    return _serialize_team(team)


@router.put("/teams/{team_id}", response_model=SchedulingTeamResponse)
def update_team(
    team_id: str,
    body: SchedulingTeamUpdateRequest,
    auth: AuthContext = Depends(require_roles(WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = SchedulingResourceService(db)
    try:
        team = service.update_team(auth.tenant_id, team_id, body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _serialize_team(team)


@router.delete("/teams/{team_id}")
def delete_team(
    team_id: str,
    auth: AuthContext = Depends(require_roles(WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = SchedulingResourceService(db)
    try:
        service.delete_team(auth.tenant_id, team_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "deleted"}


@router.post("/teams/{team_id}/members", response_model=SchedulingTeamMemberResponse)
def add_team_member(
    team_id: str,
    body: SchedulingTeamMemberAddRequest,
    auth: AuthContext = Depends(require_roles(WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = SchedulingResourceService(db)
    try:
        member = service.add_team_member(
            tenant_id=auth.tenant_id,
            team_id=team_id,
            resource_id=body.resource_id,
            priority=body.priority,
            is_active=body.is_active,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "id": member.id,
        "team_id": member.team_id,
        "resource_id": member.resource_id,
        "priority": member.priority,
        "is_active": member.is_active,
        "created_at": member.created_at,
        "resource_name": member.resource.name if member.resource else None,
        "resource_email": member.resource.email if member.resource else None,
    }


@router.delete("/teams/{team_id}/members/{resource_id}")
def remove_team_member(
    team_id: str,
    resource_id: str,
    auth: AuthContext = Depends(require_roles(WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = SchedulingResourceService(db)
    try:
        service.remove_team_member(auth.tenant_id, team_id, resource_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "deleted"}


# -----------------------------------------------------------------------------
# Excepciones de Disponibilidad
# -----------------------------------------------------------------------------
@router.get("/exceptions", response_model=list[SchedulingAvailabilityExceptionResponse])
def list_exceptions(
    resource_id: Optional[str] = Query(None),
    auth: AuthContext = Depends(require_roles(READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = SchedulingResourceService(db)
    exceptions = service.list_exceptions(auth.tenant_id, resource_id=resource_id)
    return [_serialize_exception(exc) for exc in exceptions]


@router.post("/exceptions", response_model=SchedulingAvailabilityExceptionResponse, status_code=status.HTTP_201_CREATED)
def create_exception(
    body: SchedulingAvailabilityExceptionCreateRequest,
    auth: AuthContext = Depends(require_roles(WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = SchedulingResourceService(db)
    try:
        exc = service.create_exception(
            tenant_id=auth.tenant_id,
            exception_date=body.exception_date,
            exception_type=body.exception_type,
            resource_id=body.resource_id,
            start_time=body.start_time,
            end_time=body.end_time,
            reason=body.reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_exception(exc)


@router.delete("/exceptions/{exception_id}")
def delete_exception(
    exception_id: str,
    auth: AuthContext = Depends(require_roles(WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = SchedulingResourceService(db)
    try:
        service.delete_exception(auth.tenant_id, exception_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "deleted"}


# -----------------------------------------------------------------------------
# Agentes de IA Scheduling Config
# -----------------------------------------------------------------------------
@router.get("/agents/{agent_id}", response_model=AgentSchedulingConfigResponse)
def get_agent_scheduling_config(
    agent_id: str,
    auth: AuthContext = Depends(require_roles(READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = SchedulingResourceService(db)
    cfg = service.get_agent_config(auth.tenant_id, agent_id)
    if not cfg:
        # Return default active configuration
        return {
            "id": "default",
            "tenant_id": auth.tenant_id,
            "agent_id": agent_id,
            "provider": "google_calendar",
            "scheduling_config_id": None,
            "resource_id": None,
            "team_id": None,
            "routing_strategy": "single",
            "duration_minutes": 30,
            "allow_check_availability": True,
            "allow_create_booking": True,
            "allow_reschedule": True,
            "allow_cancel": True,
            "is_active": True,
            "created_at": None,
            "updated_at": None,
            "resource_name": None,
            "team_name": None,
        }
    return _serialize_agent_config(cfg)


@router.put("/agents/{agent_id}", response_model=AgentSchedulingConfigResponse)
def upsert_agent_scheduling_config(
    agent_id: str,
    body: AgentSchedulingConfigUpsertRequest,
    auth: AuthContext = Depends(require_roles(WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = SchedulingResourceService(db)
    cfg = service.upsert_agent_config(
        tenant_id=auth.tenant_id,
        agent_id=agent_id,
        payload=body.model_dump(exclude_unset=True),
    )
    return _serialize_agent_config(cfg)


# -----------------------------------------------------------------------------
# Disponibilidad (Slot Lookup)
# -----------------------------------------------------------------------------
@router.get("/availability")
def get_availability_slots(
    date: str = Query(..., description="Target date in YYYY-MM-DD format"),
    jornada: Optional[str] = Query(None),
    reference_datetime: Optional[str] = Query(None),
    resource_id: Optional[str] = Query(None),
    team_id: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
    auth: AuthContext = Depends(require_roles(READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = SchedulingAvailabilityService(db)
    return service.get_available_slots(
        tenant_id=auth.tenant_id,
        date_input=date,
        jornada=jornada,
        reference_datetime=reference_datetime,
        resource_id=resource_id,
        team_id=team_id,
        agent_id=agent_id,
    )


# -----------------------------------------------------------------------------
# Providers & Capabilities
# -----------------------------------------------------------------------------
@router.get("/providers", response_model=list[SchedulingProviderCapabilitiesResponse])
def list_providers_with_capabilities(
    auth: AuthContext = Depends(require_roles(READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    resolver = SchedulingProviderResolver(db)
    calcom_admin = resolver.resolve_admin_provider(auth.tenant_id, "calcom")
    google_admin = resolver.resolve_admin_provider(auth.tenant_id, "google_calendar")
    return [
        {"provider": "google_calendar", **google_admin.capabilities().to_dict()},
        {"provider": "calcom", **calcom_admin.capabilities().to_dict()},
    ]


# -----------------------------------------------------------------------------
# Schedules (Availability Profiles)
# -----------------------------------------------------------------------------
@router.get("/schedules", response_model=list[SchedulingScheduleResponse])
def list_schedules(
    provider: Optional[str] = Query(None),
    auth: AuthContext = Depends(require_roles(READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    # First query local projections
    stmt = select(TenantSchedulingSchedule).where(
        TenantSchedulingSchedule.tenant_id == auth.tenant_id,
        TenantSchedulingSchedule.sync_status != "remote_deleted",
    )
    if provider:
        stmt = stmt.where(TenantSchedulingSchedule.provider == provider)
    local_schedules = list(db.scalars(stmt))
    if local_schedules:
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
            for s in local_schedules
        ]

    admin = SchedulingProviderResolver(db).resolve_admin_provider(auth.tenant_id, provider)
    schedules = admin.list_schedules()
    return [
        {
            "id": str(s.get("id")),
            "tenant_id": auth.tenant_id,
            "provider": provider or "calcom",
            "name": s.get("name", "Horario"),
            "timezone": s.get("timeZone", "America/Bogota"),
            "working_hours": s.get("availability") or s.get("working_hours_json"),
            "overrides": s.get("overrides") or s.get("dateOverrides"),
            "provider_schedule_id": str(s.get("id")),
            "is_default": bool(s.get("isDefault", False)),
            "is_active": True,
            "sync_status": "synced",
            "last_synced_at": None,
        }
        for s in schedules
    ]


@router.post("/schedules", response_model=SchedulingScheduleResponse, status_code=status.HTTP_201_CREATED)
def create_schedule(
    body: SchedulingScheduleCreateRequest,
    provider: Optional[str] = Query(None),
    auth: AuthContext = Depends(require_roles(WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    admin = SchedulingProviderResolver(db).resolve_admin_provider(auth.tenant_id, provider)
    created = admin.create_schedule(body.model_dump(exclude_unset=True))
    return {
        "id": str(created.get("id", "new")),
        "tenant_id": auth.tenant_id,
        "provider": provider or "calcom",
        "name": created.get("name", body.name),
        "timezone": created.get("timeZone", body.timezone),
        "working_hours": created.get("availability") or body.working_hours,
        "overrides": created.get("overrides") or body.overrides,
        "provider_schedule_id": str(created.get("id", "")),
        "is_default": bool(created.get("isDefault", body.is_default)),
        "is_active": True,
        "sync_status": "synced",
        "last_synced_at": None,
    }


@router.patch("/schedules/{schedule_id}", response_model=SchedulingScheduleResponse)
def update_schedule(
    schedule_id: str,
    body: SchedulingScheduleUpdateRequest,
    provider: Optional[str] = Query(None),
    auth: AuthContext = Depends(require_roles(WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    admin = SchedulingProviderResolver(db).resolve_admin_provider(auth.tenant_id, provider)
    try:
        updated = admin.update_schedule(schedule_id, body.model_dump(exclude_unset=True))
    except (ValueError, SchedulingNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {
        "id": str(schedule_id),
        "tenant_id": auth.tenant_id,
        "provider": provider or "calcom",
        "name": updated.get("name", body.name or "Horario"),
        "timezone": updated.get("timeZone", body.timezone or "America/Bogota"),
        "working_hours": updated.get("availability") or body.working_hours,
        "overrides": updated.get("overrides") or body.overrides,
        "provider_schedule_id": str(schedule_id),
        "is_default": bool(updated.get("isDefault", False)),
        "is_active": True,
        "sync_status": "synced",
        "last_synced_at": None,
    }


@router.delete("/schedules/{schedule_id}")
def delete_schedule(
    schedule_id: str,
    provider: Optional[str] = Query(None),
    auth: AuthContext = Depends(require_roles(WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    admin = SchedulingProviderResolver(db).resolve_admin_provider(auth.tenant_id, provider)
    try:
        admin.delete_schedule(schedule_id)
    except (ValueError, SchedulingNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "deleted"}


# -----------------------------------------------------------------------------
# Event Types (Tipos de Cita)
# -----------------------------------------------------------------------------
@router.get("/event-types", response_model=list[SchedulingEventTypeResponse])
def list_event_types(
    provider: Optional[str] = Query(None),
    auth: AuthContext = Depends(require_roles(READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    stmt = select(TenantSchedulingEventType).where(
        TenantSchedulingEventType.tenant_id == auth.tenant_id,
        TenantSchedulingEventType.sync_status != "remote_deleted",
    )
    if provider:
        stmt = stmt.where(TenantSchedulingEventType.provider == provider)
    local_ets = list(db.scalars(stmt))

    if local_ets:
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
            for et in local_ets
        ]

    admin = SchedulingProviderResolver(db).resolve_admin_provider(auth.tenant_id, provider)
    ets = admin.list_event_types()
    return [
        {
            "id": str(e.get("id")),
            "tenant_id": auth.tenant_id,
            "provider": provider or "calcom",
            "name": e.get("title") or e.get("name", "Tipo de cita"),
            "slug": e.get("slug", "cita"),
            "description": e.get("description"),
            "duration_minutes": int(e.get("length") or e.get("duration", 30)),
            "slot_interval_minutes": int(e.get("slotInterval", 30)),
            "buffer_before_minutes": int(e.get("beforeEventBuffer", 0)),
            "buffer_after_minutes": int(e.get("afterEventBuffer", 0)),
            "minimum_notice_minutes": int(e.get("minimumBookingNotice", 60)),
            "timezone": "America/Bogota",
            "local_schedule_id": None,
            "local_team_id": None,
            "provider_event_type_id": str(e.get("id")),
            "provider_event_type_slug": e.get("slug"),
            "is_active": not bool(e.get("hidden", False)),
            "sync_status": "synced",
            "last_synced_at": None,
        }
        for e in ets
    ]


@router.post("/event-types", response_model=SchedulingEventTypeResponse, status_code=status.HTTP_201_CREATED)
def create_event_type(
    body: SchedulingEventTypeCreateRequest,
    provider: Optional[str] = Query(None),
    auth: AuthContext = Depends(require_roles(WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    admin = SchedulingProviderResolver(db).resolve_admin_provider(auth.tenant_id, provider)
    payload = {
        "title": body.name,
        "slug": body.slug,
        "description": body.description,
        "length": body.duration_minutes,
        "slotInterval": body.slot_interval_minutes,
        "beforeEventBuffer": body.buffer_before_minutes,
        "afterEventBuffer": body.buffer_after_minutes,
        "minimumBookingNotice": body.minimum_notice_minutes,
    }
    created = admin.create_event_type(payload)
    et_id = str(created.get("id", "new"))
    return {
        "id": et_id,
        "tenant_id": auth.tenant_id,
        "provider": provider or "calcom",
        "name": created.get("title") or created.get("name", body.name),
        "slug": created.get("slug", body.slug),
        "description": created.get("description", body.description),
        "duration_minutes": int(created.get("length") or body.duration_minutes),
        "slot_interval_minutes": int(created.get("slotInterval") or body.slot_interval_minutes),
        "buffer_before_minutes": int(created.get("beforeEventBuffer") or body.buffer_before_minutes),
        "buffer_after_minutes": int(created.get("afterEventBuffer") or body.buffer_after_minutes),
        "minimum_notice_minutes": int(created.get("minimumBookingNotice") or body.minimum_notice_minutes),
        "timezone": "America/Bogota",
        "local_schedule_id": body.local_schedule_id,
        "local_team_id": body.local_team_id,
        "provider_event_type_id": et_id,
        "provider_event_type_slug": created.get("slug", body.slug),
        "is_active": body.is_active,
        "sync_status": "synced",
        "last_synced_at": None,
    }


@router.patch("/event-types/{event_type_id}", response_model=SchedulingEventTypeResponse)
def update_event_type(
    event_type_id: str,
    body: SchedulingEventTypeUpdateRequest,
    provider: Optional[str] = Query(None),
    auth: AuthContext = Depends(require_roles(WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    admin = SchedulingProviderResolver(db).resolve_admin_provider(auth.tenant_id, provider)
    payload = body.model_dump(exclude_unset=True)
    if "duration_minutes" in payload:
        payload["length"] = payload["duration_minutes"]
    if "name" in payload:
        payload["title"] = payload["name"]
    try:
        updated = admin.update_event_type(event_type_id, payload)
    except (ValueError, SchedulingNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {
        "id": str(event_type_id),
        "tenant_id": auth.tenant_id,
        "provider": provider or "calcom",
        "name": updated.get("title") or updated.get("name", body.name or "Tipo de cita"),
        "slug": updated.get("slug", body.slug or "cita"),
        "description": updated.get("description", body.description),
        "duration_minutes": int(updated.get("length") or body.duration_minutes or 30),
        "slot_interval_minutes": int(updated.get("slotInterval") or body.slot_interval_minutes or 30),
        "buffer_before_minutes": int(updated.get("beforeEventBuffer") or body.buffer_before_minutes or 0),
        "buffer_after_minutes": int(updated.get("afterEventBuffer") or body.buffer_after_minutes or 0),
        "minimum_notice_minutes": int(updated.get("minimumBookingNotice") or body.minimum_notice_minutes or 60),
        "timezone": "America/Bogota",
        "local_schedule_id": body.local_schedule_id,
        "local_team_id": body.local_team_id,
        "provider_event_type_id": str(event_type_id),
        "provider_event_type_slug": updated.get("slug"),
        "is_active": body.is_active if body.is_active is not None else True,
        "sync_status": "synced",
        "last_synced_at": None,
    }


@router.delete("/event-types/{event_type_id}")
def delete_event_type(
    event_type_id: str,
    provider: Optional[str] = Query(None),
    auth: AuthContext = Depends(require_roles(WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    admin = SchedulingProviderResolver(db).resolve_admin_provider(auth.tenant_id, provider)
    try:
        admin.delete_event_type(event_type_id)
    except (ValueError, SchedulingNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "deleted"}


# -----------------------------------------------------------------------------
# Cal.com Discovery & Sync
# -----------------------------------------------------------------------------
@router.post("/providers/calcom/sync", response_model=CalComDiscoveryResponse)
def sync_calcom(
    auth: AuthContext = Depends(require_roles(WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = CalComSyncService(db)
    try:
        return service.sync(auth.tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/providers/calcom/discovery", response_model=CalComDiscoveryResponse)
def get_calcom_discovery(
    auth: AuthContext = Depends(require_roles(READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    admin = SchedulingProviderResolver(db).resolve_admin_provider(auth.tenant_id, "calcom")
    try:
        data = admin.discover()
        return {
            "status": "success",
            "counts": data.get("counts", {}),
            "account": data.get("user"),
            "last_synced_at": None,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
