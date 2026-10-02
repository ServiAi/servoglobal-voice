"""Scheduling contracts: what callers and the HTTP layer may rely on.

Framework-light on purpose (dataclasses + pydantic only; no SQLAlchemy, FastAPI,
Google, Cal.com, CRM or Notifications). ``scheduling.public`` re-exports these.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

JsonValue = Any  # JSON-compatible value inside booking_fields_responses


# --------------------------------------------------------------------------
# Commands and DTOs (frozen, ORM-free)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class CreateBookingCommand:
    """Everything the booking flow needs, independent of any HTTP schema."""

    start: str
    attendee_name: str
    attendee_email: str
    timezone: str = "America/Bogota"
    attendee_phone: str | None = None
    notes: str | None = None
    event_type_id: int | None = None
    event_type_slug: str | None = None
    username: str | None = None
    team_slug: str | None = None
    organization_slug: str | None = None
    booking_fields_responses: Mapping[str, JsonValue] = field(default_factory=dict)
    scheduling_resource_id: str | None = None
    scheduling_team_id: str | None = None


    @classmethod
    def validated(cls, **fields: Any) -> CreateBookingCommand:
        """Build a command from untrusted values (an LLM tool call, a voice
        webhook). Raises ``pydantic.ValidationError`` for a malformed request,
        with the same constraints the HTTP contract always had."""
        return cls(**_CreateBookingModel(**fields).model_dump())


class _CreateBookingModel(BaseModel):
    start: str
    timezone: str = "America/Bogota"
    event_type_id: int | None = None
    event_type_slug: str | None = None
    username: str | None = None
    team_slug: str | None = None
    organization_slug: str | None = None
    attendee_name: str = Field(..., min_length=1, max_length=255)
    attendee_email: str = Field(..., min_length=3, max_length=255)
    attendee_phone: str | None = Field(None, max_length=80)
    booking_fields_responses: dict[str, Any] = Field(default_factory=dict)
    scheduling_resource_id: str | None = None
    scheduling_team_id: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class BookingCustomer:
    """The lead's contact as Scheduling sees it (CRM owns the real rows)."""

    lead_id: str
    contact_id: str
    tenant_id: str
    name: str | None
    email: str | None
    phone: str | None


@dataclass(frozen=True)
class BookingSummary:
    id: str
    status: str
    start_at: datetime


@dataclass(frozen=True)
class BookingView:
    """A booking, without provider secrets or the raw ``metadata_json``."""

    id: str
    tenant_id: str
    lead_id: str | None
    contact_id: str | None
    provider: str
    provider_booking_id: str | None
    provider_booking_uid: str | None
    status: str
    start_at: datetime
    end_at: datetime | None
    timezone: str
    duration_minutes: int | None
    meeting_url: str | None
    attendee_name: str
    attendee_email: str
    attendee_phone: str | None
    host_name: str | None
    title: str | None
    calendar_mode: str
    created_at: datetime
    # The only metadata key Notifications is allowed to read.
    notification_custom: Mapping[str, JsonValue] = field(default_factory=dict)


# --------------------------------------------------------------------------
# HTTP contracts owned by Scheduling (moved from app.schemas.integrations)
# --------------------------------------------------------------------------

class BookingConfigRequest(BaseModel):
    cal_api_key: str | None = Field(None, max_length=500)
    status: str = "active"
    calendar_mode: str = "cal_managed"
    cal_api_version: str = "2024-08-13"
    organization_slug: str | None = Field(None, max_length=120)
    default_event_type_id: int | None = None
    default_event_type_slug: str | None = Field(None, max_length=160)
    default_username: str | None = Field(None, max_length=160)
    default_team_slug: str | None = Field(None, max_length=160)
    default_timezone: str = "America/Bogota"
    default_language: str = "es"
    default_location_type: str | None = Field(None, max_length=80)
    default_length_minutes: int = Field(30, ge=5, le=480)


class BookingConfigResponse(BaseModel):
    provider: str = "calcom"
    status: str
    calendar_mode: str
    has_secret: bool
    default_event_type_id: int | None = None
    default_event_type_slug: str | None = None
    default_username: str | None = None
    default_team_slug: str | None = None
    organization_slug: str | None = None
    default_timezone: str
    default_language: str
    default_location_type: str | None = None
    default_length_minutes: int
    last_health_check_at: datetime | None = None
    last_error_message: str | None = None


class CalComTestResponse(BaseModel):
    status: str
    error_message: str | None = None


class GoogleCalendarConnectUrlResponse(BaseModel):
    url: str


class GoogleCalendarConnectionResponse(BaseModel):
    id: str
    status: str
    google_account_email: str | None = None
    calendar_id: str
    calendar_summary: str | None = None
    scopes: list[str] = Field(default_factory=list)
    last_sync_at: datetime | None = None
    last_error_message: str | None = None
    has_tokens: bool


class TenantGoogleCalendarResponse(BaseModel):
    id: str
    tenant_id: str
    connection_id: str
    google_calendar_id: str
    summary: str | None = None
    description: str | None = None
    time_zone: str | None = None
    is_primary: bool
    is_blocking: bool
    is_booking_destination: bool
    access_role: str | None = None
    created_at: datetime
    updated_at: datetime


class TenantGoogleCalendarUpdateRequest(BaseModel):
    is_blocking: bool | None = None
    is_booking_destination: bool | None = None


class GoogleCalendarSyncResponse(BaseModel):
    connection_id: str
    synced_count: int
    calendars: list[TenantGoogleCalendarResponse]


class SchedulingResourceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    resource_type: str = Field(default="user", max_length=40)
    team: str | None = Field(None, max_length=80)
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=80)
    priority: int = 1
    timezone: str = "America/Bogota"
    capacity: int = 1
    working_hours: dict[str, Any] | None = None


class SchedulingResourceCalendarResponse(BaseModel):
    id: str
    resource_id: str
    calendar_id: str
    is_blocking: bool
    is_destination: bool
    created_at: datetime


class SchedulingResourceResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    resource_type: str
    team: str | None = None
    email: str | None = None
    phone: str | None = None
    priority: int
    is_active: bool
    timezone: str
    capacity: int
    total_assigned_count: int
    last_assigned_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    calendars: list[SchedulingResourceCalendarResponse] = Field(default_factory=list)


class SchedulingResourceCalendarAssignRequest(BaseModel):
    calendar_id: str
    is_blocking: bool = True
    is_destination: bool = True
