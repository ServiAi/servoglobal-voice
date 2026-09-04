from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class TimeSlotInterval(BaseModel):
    start: str = Field(..., description="HH:MM format, e.g. 08:00")
    end: str = Field(..., description="HH:MM format, e.g. 12:00")


class WeeklyWorkingHoursSchema(BaseModel):
    monday: list[TimeSlotInterval] = Field(default_factory=list)
    tuesday: list[TimeSlotInterval] = Field(default_factory=list)
    wednesday: list[TimeSlotInterval] = Field(default_factory=list)
    thursday: list[TimeSlotInterval] = Field(default_factory=list)
    friday: list[TimeSlotInterval] = Field(default_factory=list)
    saturday: list[TimeSlotInterval] = Field(default_factory=list)
    sunday: list[TimeSlotInterval] = Field(default_factory=list)


class TenantSchedulingConfigResponse(BaseModel):
    id: str
    tenant_id: str
    timezone: str = "America/Bogota"
    default_duration_minutes: int = 30
    slot_interval_minutes: int = 30
    buffer_before_minutes: int = 0
    buffer_after_minutes: int = 0
    minimum_notice_minutes: int = 60
    maximum_booking_days: int = 30
    routing_strategy: str = "single"
    default_resource_id: Optional[str] = None
    default_team_id: Optional[str] = None
    working_hours_json: Optional[dict[str, Any]] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class TenantSchedulingConfigUpdateRequest(BaseModel):
    timezone: Optional[str] = Field(None, max_length=80)
    default_duration_minutes: Optional[int] = Field(None, ge=5, le=480)
    slot_interval_minutes: Optional[int] = Field(None, ge=5, le=480)
    buffer_before_minutes: Optional[int] = Field(None, ge=0, le=240)
    buffer_after_minutes: Optional[int] = Field(None, ge=0, le=240)
    minimum_notice_minutes: Optional[int] = Field(None, ge=0, le=10080)
    maximum_booking_days: Optional[int] = Field(None, ge=1, le=365)
    routing_strategy: Optional[str] = Field(None, max_length=40)
    default_resource_id: Optional[str] = None
    default_team_id: Optional[str] = None
    working_hours_json: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None


class SchedulingResourceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    resource_type: str = Field(default="user", max_length=40)
    team: Optional[str] = Field(None, max_length=80)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=80)
    priority: int = 1
    timezone: str = "America/Bogota"
    capacity: int = 1
    working_hours: Optional[dict[str, Any]] = None


class SchedulingResourceUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=160)
    resource_type: Optional[str] = Field(None, max_length=40)
    team: Optional[str] = Field(None, max_length=80)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=80)
    priority: Optional[int] = None
    timezone: Optional[str] = Field(None, max_length=80)
    capacity: Optional[int] = None
    is_active: Optional[bool] = None
    working_hours: Optional[dict[str, Any]] = None


class SchedulingResourceCalendarResponse(BaseModel):
    id: str
    resource_id: str
    calendar_id: str
    is_blocking: bool
    is_destination: bool
    created_at: datetime
    google_calendar_id: Optional[str] = None
    summary: Optional[str] = None


class SchedulingResourceResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    resource_type: str
    team: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    priority: int
    is_active: bool
    timezone: str
    capacity: int
    working_hours: Optional[dict[str, Any]] = None
    total_assigned_count: int
    last_assigned_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    calendars: list[SchedulingResourceCalendarResponse] = Field(default_factory=list)


class SchedulingResourceCalendarAssignRequest(BaseModel):
    calendar_id: str
    is_blocking: bool = True
    is_destination: bool = True


class SchedulingTeamMemberResponse(BaseModel):
    id: str
    team_id: str
    resource_id: str
    priority: int
    is_active: bool
    created_at: datetime
    resource_name: Optional[str] = None
    resource_email: Optional[str] = None


class SchedulingTeamResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: Optional[str] = None
    routing_strategy: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    members: list[SchedulingTeamMemberResponse] = Field(default_factory=list)


class SchedulingTeamCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    description: Optional[str] = None
    routing_strategy: str = Field(default="round_robin", max_length=40)
    is_active: bool = True


class SchedulingTeamUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=160)
    description: Optional[str] = None
    routing_strategy: Optional[str] = Field(None, max_length=40)
    is_active: Optional[bool] = None


class SchedulingTeamMemberAddRequest(BaseModel):
    resource_id: str
    priority: int = 1
    is_active: bool = True


class SchedulingAvailabilityExceptionResponse(BaseModel):
    id: str
    tenant_id: str
    resource_id: Optional[str] = None
    exception_date: date
    exception_type: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    resource_name: Optional[str] = None


class SchedulingAvailabilityExceptionCreateRequest(BaseModel):
    resource_id: Optional[str] = None
    exception_date: date
    exception_type: str = Field(default="unavailable", pattern="^(unavailable|custom_hours)$")
    start_time: Optional[str] = Field(None, max_length=8)
    end_time: Optional[str] = Field(None, max_length=8)
    reason: Optional[str] = Field(None, max_length=255)


class AgentSchedulingConfigResponse(BaseModel):
    id: str
    tenant_id: str
    agent_id: str
    provider: str
    scheduling_config_id: Optional[str] = None
    resource_id: Optional[str] = None
    team_id: Optional[str] = None
    routing_strategy: str
    duration_minutes: Optional[int] = None
    allow_check_availability: bool
    allow_create_booking: bool
    allow_reschedule: bool
    allow_cancel: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
    resource_name: Optional[str] = None
    team_name: Optional[str] = None


class AgentSchedulingConfigUpsertRequest(BaseModel):
    provider: str = Field(default="google_calendar", max_length=40)
    scheduling_config_id: Optional[str] = None
    resource_id: Optional[str] = None
    team_id: Optional[str] = None
    routing_strategy: str = Field(default="single", max_length=40)
    duration_minutes: Optional[int] = Field(None, ge=5, le=480)
    allow_check_availability: bool = True
    allow_create_booking: bool = True
    allow_reschedule: bool = True
    allow_cancel: bool = True
    is_active: bool = True


class SchedulingDashboardSummaryResponse(BaseModel):
    active_resources_count: int
    teams_count: int
    connected_calendars_count: int
    upcoming_bookings_count: int
    google_connected: bool
    availability_configured: bool
    agents_count: int
    alerts: list[str] = Field(default_factory=list)
