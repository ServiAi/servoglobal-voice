"""Scheduling persistence: booking configs, Google Calendar connections,
resources, teams, schedules, event types, agent scheduling and the bookings
themselves (``crm_bookings`` / ``crm_booking_events``).

Same tables, columns, FKs, indexes and constraints as before the move (code
ownership only; no schema change). The FKs to ``crm_leads``/``crm_contacts``
stay at the database level, but Scheduling never navigates CRM rows: it holds
ids and asks ``crm.public`` for DTOs. ORM relationships below are internal to
Scheduling (plus the shared ``Tenant``/``User`` anchors).
"""

from __future__ import annotations

from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, _utcnow, _uuid


class TenantBookingConfig(Base, TimestampMixin):
    __tablename__ = "tenant_booking_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", name="uq_tenant_booking_configs_tenant_provider"),
        Index("ix_tenant_booking_configs_tenant_provider", "tenant_id", "provider"),
        Index("ix_tenant_booking_configs_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="calcom")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="inactive")
    calendar_mode: Mapped[str] = mapped_column(String(40), nullable=False, default="cal_managed")
    cal_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    cal_api_version: Mapped[str] = mapped_column(String(40), nullable=False, default="2024-08-13")
    organization_slug: Mapped[str | None] = mapped_column(String(120), nullable=True)
    default_event_type_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    default_event_type_slug: Mapped[str | None] = mapped_column(String(160), nullable=True)
    default_username: Mapped[str | None] = mapped_column(String(160), nullable=True)
    default_team_slug: Mapped[str | None] = mapped_column(String(160), nullable=True)
    default_timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="America/Bogota")
    default_language: Mapped[str] = mapped_column(String(16), nullable=False, default="es")
    default_location_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    default_length_minutes: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=30)
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant = relationship("Tenant")


class TenantGoogleCalendarConnection(Base, TimestampMixin):
    __tablename__ = "tenant_google_calendar_connections"
    __table_args__ = (
        Index("ix_tenant_google_calendar_connections_tenant_status", "tenant_id", "status"),
        Index("ix_tenant_google_calendar_connections_tenant_user", "tenant_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="connected")
    google_account_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    calendar_id: Mapped[str] = mapped_column(String(255), nullable=False, default="primary")
    calendar_summary: Mapped[str | None] = mapped_column(String(255), nullable=True)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scopes_json: Mapped[list] = mapped_column(sa.JSON, nullable=False, default=list)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant = relationship("Tenant")
    user = relationship("User")
    calendars = relationship("TenantGoogleCalendar", back_populates="connection", cascade="all, delete-orphan")


class TenantGoogleCalendar(Base, TimestampMixin):
    __tablename__ = "tenant_google_calendars"
    __table_args__ = (
        UniqueConstraint("connection_id", "google_calendar_id", name="uq_tenant_google_calendars_conn_cal"),
        Index("ix_tenant_google_calendars_tenant_conn", "tenant_id", "connection_id"),
        Index("ix_tenant_google_calendars_tenant_blocking", "tenant_id", "is_blocking"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    connection_id: Mapped[str] = mapped_column(ForeignKey("tenant_google_calendar_connections.id"), nullable=False)
    google_calendar_id: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    time_zone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_primary: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    is_blocking: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    is_booking_destination: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    access_role: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sync_token: Mapped[str | None] = mapped_column(String(255), nullable=True)

    tenant = relationship("Tenant")
    connection = relationship("TenantGoogleCalendarConnection", back_populates="calendars")


class TenantSchedulingResource(Base, TimestampMixin):
    __tablename__ = "tenant_scheduling_resources"
    __table_args__ = (
        Index("ix_tenant_scheduling_resources_tenant_team", "tenant_id", "team"),
        Index("ix_tenant_scheduling_resources_tenant_active", "tenant_id", "is_active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False, default="user")
    team: Mapped[str | None] = mapped_column(String(80), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    priority: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="America/Bogota")
    capacity: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    working_hours_json: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    total_assigned_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    last_assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant")
    resource_calendars = relationship("TenantSchedulingResourceCalendar", back_populates="resource", cascade="all, delete-orphan")


class TenantSchedulingResourceCalendar(Base):
    __tablename__ = "tenant_scheduling_resource_calendars"
    __table_args__ = (
        UniqueConstraint("resource_id", "calendar_id", name="uq_tenant_resource_calendars_res_cal"),
        Index("ix_tenant_scheduling_resource_calendars_tenant_resource", "tenant_id", "resource_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    resource_id: Mapped[str] = mapped_column(ForeignKey("tenant_scheduling_resources.id", ondelete="CASCADE"), nullable=False)
    calendar_id: Mapped[str] = mapped_column(ForeignKey("tenant_google_calendars.id", ondelete="CASCADE"), nullable=False)
    is_blocking: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    is_destination: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    tenant = relationship("Tenant")
    resource = relationship("TenantSchedulingResource", back_populates="resource_calendars")
    calendar = relationship("TenantGoogleCalendar")


class TenantSchedulingConfig(Base, TimestampMixin):
    __tablename__ = "tenant_scheduling_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_tenant_scheduling_configs_tenant"),
        Index("ix_tenant_scheduling_configs_tenant", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="America/Bogota")
    default_duration_minutes: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=30)
    slot_interval_minutes: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=30)
    buffer_before_minutes: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    buffer_after_minutes: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    minimum_notice_minutes: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=60)
    maximum_booking_days: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=30)
    routing_strategy: Mapped[str] = mapped_column(String(40), nullable=False, default="single")
    default_resource_id: Mapped[str | None] = mapped_column(ForeignKey("tenant_scheduling_resources.id", ondelete="SET NULL"), nullable=True)
    default_team_id: Mapped[str | None] = mapped_column(ForeignKey("tenant_scheduling_teams.id", ondelete="SET NULL"), nullable=True)
    working_hours_json: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)

    tenant = relationship("Tenant")
    default_resource = relationship("TenantSchedulingResource", foreign_keys=[default_resource_id])
    default_team = relationship("TenantSchedulingTeam", foreign_keys=[default_team_id])


class TenantSchedulingTeam(Base, TimestampMixin):
    __tablename__ = "tenant_scheduling_teams"
    __table_args__ = (
        Index("ix_tenant_scheduling_teams_tenant", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    routing_strategy: Mapped[str] = mapped_column(String(40), nullable=False, default="round_robin")
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)

    tenant = relationship("Tenant")
    members = relationship("TenantSchedulingTeamMember", back_populates="team", cascade="all, delete-orphan")


class TenantSchedulingTeamMember(Base):
    __tablename__ = "tenant_scheduling_team_members"
    __table_args__ = (
        UniqueConstraint("team_id", "resource_id", name="uq_tenant_team_members_team_resource"),
        Index("ix_tenant_scheduling_team_members_tenant_team", "tenant_id", "team_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    team_id: Mapped[str] = mapped_column(ForeignKey("tenant_scheduling_teams.id", ondelete="CASCADE"), nullable=False)
    resource_id: Mapped[str] = mapped_column(ForeignKey("tenant_scheduling_resources.id", ondelete="CASCADE"), nullable=False)
    priority: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    tenant = relationship("Tenant")
    team = relationship("TenantSchedulingTeam", back_populates="members")
    resource = relationship("TenantSchedulingResource")


class TenantSchedulingAvailabilityException(Base, TimestampMixin):
    __tablename__ = "tenant_scheduling_exceptions"
    __table_args__ = (
        Index("ix_tenant_scheduling_exceptions_tenant_date", "tenant_id", "exception_date"),
        Index("ix_tenant_scheduling_exceptions_resource_date", "resource_id", "exception_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(ForeignKey("tenant_scheduling_resources.id", ondelete="CASCADE"), nullable=True)
    exception_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    exception_type: Mapped[str] = mapped_column(String(40), nullable=False, default="unavailable")
    start_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    end_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    tenant = relationship("Tenant")
    resource = relationship("TenantSchedulingResource")


class TenantSchedulingSchedule(Base, TimestampMixin):
    __tablename__ = "tenant_scheduling_schedules"
    __table_args__ = (
        Index("ix_tenant_scheduling_schedules_tenant_id", "tenant_id"),
        Index("ix_tenant_scheduling_schedules_tenant_provider", "tenant_id", "provider"),
        Index("ix_tenant_scheduling_schedules_tenant_provider_ext", "tenant_id", "provider", "provider_schedule_id"),
        Index("ix_tenant_scheduling_schedules_tenant_status", "tenant_id", "sync_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="calcom")
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="America/Bogota")
    working_hours_json: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    overrides_json: Mapped[list | None] = mapped_column(sa.JSON, nullable=True)
    provider_schedule_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_default: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(32), nullable=False, default="synced")
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant = relationship("Tenant")


class TenantSchedulingEventType(Base, TimestampMixin):
    __tablename__ = "tenant_scheduling_event_types"
    __table_args__ = (
        Index("ix_tenant_scheduling_event_types_tenant_id", "tenant_id"),
        Index("ix_tenant_scheduling_event_types_tenant_provider", "tenant_id", "provider"),
        Index("ix_tenant_scheduling_event_types_tenant_provider_ext", "tenant_id", "provider", "provider_event_type_id"),
        Index("ix_tenant_scheduling_event_types_tenant_status", "tenant_id", "sync_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="calcom")
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=30)
    slot_interval_minutes: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=30)
    buffer_before_minutes: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    buffer_after_minutes: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    minimum_notice_minutes: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=60)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="America/Bogota")
    local_schedule_id: Mapped[str | None] = mapped_column(ForeignKey("tenant_scheduling_schedules.id", ondelete="SET NULL"), nullable=True)
    local_team_id: Mapped[str | None] = mapped_column(ForeignKey("tenant_scheduling_teams.id", ondelete="SET NULL"), nullable=True)
    provider_event_type_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    provider_event_type_slug: Mapped[str | None] = mapped_column(String(160), nullable=True)
    provider_config_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(32), nullable=False, default="synced")
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant = relationship("Tenant")
    schedule = relationship("TenantSchedulingSchedule", foreign_keys=[local_schedule_id])
    team = relationship("TenantSchedulingTeam", foreign_keys=[local_team_id])


class TenantSchedulingProviderObject(Base, TimestampMixin):
    __tablename__ = "tenant_scheduling_provider_objects"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", "object_type", "external_id", name="uq_tenant_provider_object"),
        Index("ix_tenant_provider_objects_tenant_provider", "tenant_id", "provider"),
        Index("ix_tenant_provider_objects_tenant_status", "tenant_id", "sync_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    object_type: Mapped[str] = mapped_column(String(40), nullable=False)  # schedule, event_type, resource, team, membership
    local_object_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_slug: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_metadata_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    sync_status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")  # active, remote_deleted, sync_error
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant = relationship("Tenant")


class TenantAgentSchedulingConfig(Base, TimestampMixin):
    __tablename__ = "tenant_agent_scheduling_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "agent_id", name="uq_tenant_agent_scheduling_tenant_agent"),
        Index("ix_tenant_agent_scheduling_tenant_agent", "tenant_id", "agent_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="google_calendar")
    scheduling_config_id: Mapped[str | None] = mapped_column(ForeignKey("tenant_scheduling_configs.id"), nullable=True)
    event_type_id: Mapped[str | None] = mapped_column(ForeignKey("tenant_scheduling_event_types.id", ondelete="SET NULL"), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(ForeignKey("tenant_scheduling_resources.id", ondelete="SET NULL"), nullable=True)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("tenant_scheduling_teams.id", ondelete="SET NULL"), nullable=True)
    routing_strategy: Mapped[str] = mapped_column(String(40), nullable=False, default="single")
    duration_minutes: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    allow_check_availability: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    allow_create_booking: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    allow_reschedule: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    allow_cancel: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)

    tenant = relationship("Tenant")
    scheduling_config = relationship("TenantSchedulingConfig")
    event_type = relationship("TenantSchedulingEventType", foreign_keys=[event_type_id])
    resource = relationship("TenantSchedulingResource")
    team = relationship("TenantSchedulingTeam")


class TenantVoiceBookingConfig(Base, TimestampMixin):
    __tablename__ = "tenant_voice_booking_configs"
    __table_args__ = (
        Index("ix_tenant_voice_booking_configs_tenant_agent", "tenant_id", "provider_agent_id"),
        Index("ix_tenant_voice_booking_configs_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    provider_agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_booking_config_id: Mapped[str | None] = mapped_column(ForeignKey("tenant_booking_configs.id"), nullable=True)
    default_event_type_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    default_event_type_slug: Mapped[str | None] = mapped_column(String(160), nullable=True)
    default_timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="America/Bogota")
    default_jornada_rules_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    enabled_tools_json: Mapped[list] = mapped_column(sa.JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    tenant = relationship("Tenant")
    default_booking_config = relationship("TenantBookingConfig")


class CrmBooking(Base, TimestampMixin):
    __tablename__ = "crm_bookings"
    __table_args__ = (
        Index("ix_crm_bookings_tenant_lead", "tenant_id", "lead_id"),
        Index("ix_crm_bookings_tenant_contact", "tenant_id", "contact_id"),
        Index("ix_crm_bookings_tenant_provider_uid", "tenant_id", "provider_booking_uid"),
        Index("ix_crm_bookings_tenant_status", "tenant_id", "status"),
        Index("ix_crm_bookings_tenant_start", "tenant_id", "start_at"),
        Index("ix_crm_bookings_tenant_google_event", "tenant_id", "google_calendar_event_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("crm_leads.id"), nullable=True)
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("crm_contacts.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="calcom")
    provider_booking_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_booking_uid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_event_type_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    provider_event_type_slug: Mapped[str | None] = mapped_column(String(160), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="America/Bogota")
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meeting_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    location_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    attendee_name: Mapped[str] = mapped_column(String(255), nullable=False)
    attendee_email: Mapped[str] = mapped_column(String(255), nullable=False)
    attendee_phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    host_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    host_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_calendar_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    calendar_mode: Mapped[str] = mapped_column(String(40), nullable=False, default="cal_managed")
    metadata_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rescheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant")


class CrmBookingEvent(Base):
    __tablename__ = "crm_booking_events"
    __table_args__ = (
        Index("ix_crm_booking_events_tenant_booking", "tenant_id", "booking_id"),
        Index("ix_crm_booking_events_tenant_provider", "tenant_id", "provider"),
        Index("ix_crm_booking_events_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    booking_id: Mapped[str] = mapped_column(ForeignKey("crm_bookings.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="calcom")
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_summary_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    tenant = relationship("Tenant")
    booking = relationship("CrmBooking")
