from __future__ import annotations

import sqlalchemy as sa
from datetime import date, datetime
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.identity import TimestampMixin, _uuid, _utcnow


class TenantIntegration(Base, TimestampMixin):
    __tablename__ = "tenant_integrations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", name="uq_tenant_integrations_tenant_provider"),
        Index("ix_tenant_integrations_tenant_id", "tenant_id"),
        Index("ix_tenant_integrations_tenant_provider", "tenant_id", "provider"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    enabled: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="inactive")
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    config_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    secrets_json_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant = relationship("Tenant")


class TenantIntegrationEvent(Base):
    __tablename__ = "tenant_integration_events"
    __table_args__ = (
        Index("ix_tenant_integration_events_tenant_provider", "tenant_id", "provider"),
        Index("ix_tenant_integration_events_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    tenant = relationship("Tenant")


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


class TenantWhatsAppConfig(Base, TimestampMixin):
    __tablename__ = "tenant_whatsapp_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", name="uq_tenant_whatsapp_configs_tenant_provider"),
        Index("ix_tenant_whatsapp_configs_tenant_provider", "tenant_id", "provider"),
        Index("ix_tenant_whatsapp_configs_tenant_status", "tenant_id", "status"),
        Index("ix_tenant_whatsapp_configs_phone_number", "phone_number_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="whatsapp_cloud")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="inactive")
    phone_number_id: Mapped[str] = mapped_column(String(120), nullable=False)
    business_account_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    display_phone_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    default_language: Mapped[str] = mapped_column(String(16), nullable=False, default="es")
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_verify_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant = relationship("Tenant")


class TenantWhatsAppTemplate(Base, TimestampMixin):
    __tablename__ = "tenant_whatsapp_templates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "template_key", name="uq_tenant_whatsapp_templates_tenant_key"),
        Index("ix_tenant_whatsapp_templates_tenant_key", "tenant_id", "template_key"),
        Index("ix_tenant_whatsapp_templates_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    template_key: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_template_name: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False, default="transactional")
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="es")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Deprecated: kept for backward-compatible reads; approval state now lives in the typed columns below.
    variables_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    # Internal lifecycle: draft | pending | approved | rejected | disabled.
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    # Raw status string as returned by Meta: PENDING/APPROVED/REJECTED/PAUSED/DISABLED.
    meta_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_template_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="tenant_authored")
    parameter_format: Mapped[str] = mapped_column(String(16), nullable=False, default="POSITIONAL")
    header_json: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    footer_text: Mapped[str | None] = mapped_column(String(60), nullable=True)
    buttons_json: Mapped[list] = mapped_column(sa.JSON, nullable=False, default=list)
    components_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    tenant = relationship("Tenant")


class TenantWhatsAppFlow(Base, TimestampMixin):
    __tablename__ = "tenant_whatsapp_flows"
    __table_args__ = (
        UniqueConstraint("tenant_id", "flow_key", "version", name="uq_tenant_whatsapp_flows_tenant_key_version"),
        Index("ix_tenant_whatsapp_flows_tenant_status", "tenant_id", "status"),
        Index("ix_tenant_whatsapp_flows_tenant_provider", "tenant_id", "provider_flow_id"),
        Index("ix_tenant_whatsapp_flows_tenant_key", "tenant_id", "flow_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    flow_key: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    parent_flow_id: Mapped[str | None] = mapped_column(
        ForeignKey("tenant_whatsapp_flows.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    categories_json: Mapped[list] = mapped_column(sa.JSON, nullable=False, default=list)
    source_mode: Mapped[str] = mapped_column(String(24), nullable=False, default="visual")
    context_schema_id: Mapped[str | None] = mapped_column(
        ForeignKey("tenant_voice_context_schemas.id", ondelete="SET NULL"), nullable=True
    )
    context_schema_snapshot_json: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    meta_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_flow_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    builder_schema_version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    builder_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    compiled_flow_json: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    compiled_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    synced_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    validation_errors_json: Mapped[list] = mapped_column(sa.JSON, nullable=False, default=list)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant")
    parent_flow = relationship("TenantWhatsAppFlow", remote_side=[id])
    context_schema = relationship("TenantVoiceContextSchema")
    created_by_user = relationship("User")


class TenantEmailConfig(Base, TimestampMixin):
    __tablename__ = "tenant_email_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", name="uq_tenant_email_configs_tenant_provider"),
        Index("ix_tenant_email_configs_tenant_provider", "tenant_id", "provider"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="resend")
    sender_email: Mapped[str] = mapped_column(String(255), nullable=False)
    sender_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reply_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="inactive")
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant = relationship("Tenant")


class TenantEmailTemplate(Base, TimestampMixin):
    __tablename__ = "tenant_email_templates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "template_key", name="uq_tenant_email_templates_tenant_key"),
        Index("ix_tenant_email_templates_tenant_key", "tenant_id", "template_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    template_key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    html_body: Mapped[str] = mapped_column(Text, nullable=False)
    text_body: Mapped[str] = mapped_column(Text, nullable=False)
    variables_schema: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    is_marketing: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)

    tenant = relationship("Tenant")


class TenantEmailAsset(Base, TimestampMixin):
    __tablename__ = "tenant_email_assets"
    __table_args__ = (
        Index("ix_tenant_email_assets_tenant_status", "tenant_id", "status"),
        Index("ix_tenant_email_assets_storage_key", "storage_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    uploaded_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="private")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded")

    tenant = relationship("Tenant")
    uploaded_by = relationship("User")


class TenantEmailSend(Base, TimestampMixin):
    __tablename__ = "tenant_email_sends"
    __table_args__ = (
        Index("ix_tenant_email_sends_tenant_lead", "tenant_id", "lead_id"),
        Index("ix_tenant_email_sends_tenant_status", "tenant_id", "status"),
        Index("ix_tenant_email_sends_tenant_provider_email", "tenant_id", "provider_email_id"),
        Index("ix_tenant_email_sends_tenant_created_at", "tenant_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("crm_leads.id"), nullable=True)
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("crm_contacts.id"), nullable=True)
    template_id: Mapped[str | None] = mapped_column(ForeignKey("tenant_email_templates.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="resend")
    provider_email_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    to_email: Mapped[str] = mapped_column(String(255), nullable=False)
    from_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant")
    lead = relationship("CrmLead")
    contact = relationship("CrmContact")
    template = relationship("TenantEmailTemplate")


class TenantEmailSendAsset(Base):
    __tablename__ = "tenant_email_send_assets"
    __table_args__ = (
        Index("ix_tenant_email_send_assets_tenant_send", "tenant_id", "email_send_id"),
        UniqueConstraint("email_send_id", "asset_id", name="uq_tenant_email_send_assets_send_asset"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    email_send_id: Mapped[str] = mapped_column(ForeignKey("tenant_email_sends.id"), nullable=False)
    asset_id: Mapped[str] = mapped_column(ForeignKey("tenant_email_assets.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    tenant = relationship("Tenant")
    email_send = relationship("TenantEmailSend")
    asset = relationship("TenantEmailAsset")


class TenantForm(Base, TimestampMixin):
    __tablename__ = "tenant_forms"
    __table_args__ = (
        Index("ix_tenant_forms_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    tenant = relationship("Tenant")
    fields: Mapped[list[TenantFormField]] = relationship(
        back_populates="form",
        cascade="all, delete-orphan",
        order_by="TenantFormField.position",
    )


class TenantFormField(Base, TimestampMixin):
    __tablename__ = "tenant_form_fields"
    __table_args__ = (
        Index("ix_tenant_form_fields_tenant_form", "tenant_id", "form_id"),
        UniqueConstraint("form_id", "key", name="uq_tenant_form_fields_form_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    form_id: Mapped[str] = mapped_column(ForeignKey("tenant_forms.id"), nullable=False)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    field_type: Mapped[str] = mapped_column(String(32), nullable=False)
    required: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    options_json: Mapped[list] = mapped_column(sa.JSON, nullable=False, default=list)
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    tenant = relationship("Tenant")
    form = relationship("TenantForm", back_populates="fields")


class TenantFormToken(Base):
    __tablename__ = "tenant_form_tokens"
    __table_args__ = (
        Index("ix_tenant_form_tokens_token_hash", "token_hash"),
        Index("ix_tenant_form_tokens_tenant_lead", "tenant_id", "lead_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    form_id: Mapped[str] = mapped_column(ForeignKey("tenant_forms.id"), nullable=False)
    lead_id: Mapped[str] = mapped_column(ForeignKey("crm_leads.id"), nullable=False)
    contact_id: Mapped[str] = mapped_column(ForeignKey("crm_contacts.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    tenant = relationship("Tenant")
    form = relationship("TenantForm")
    lead = relationship("CrmLead")
    contact = relationship("CrmContact")


class TenantFormSubmission(Base):
    __tablename__ = "tenant_form_submissions"
    __table_args__ = (
        Index("ix_tenant_form_submissions_tenant_lead", "tenant_id", "lead_id"),
        Index("ix_tenant_form_submissions_token", "token_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    form_id: Mapped[str] = mapped_column(ForeignKey("tenant_forms.id"), nullable=False)
    lead_id: Mapped[str] = mapped_column(ForeignKey("crm_leads.id"), nullable=False)
    contact_id: Mapped[str] = mapped_column(ForeignKey("crm_contacts.id"), nullable=False)
    token_id: Mapped[str] = mapped_column(ForeignKey("tenant_form_tokens.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="submitted")
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    tenant = relationship("Tenant")
    form = relationship("TenantForm")
    lead = relationship("CrmLead")
    contact = relationship("CrmContact")
    token = relationship("TenantFormToken")
    answers: Mapped[list[TenantFormSubmissionAnswer]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
    )


class TenantFormSubmissionAnswer(Base):
    __tablename__ = "tenant_form_submission_answers"
    __table_args__ = (
        Index("ix_tenant_form_submission_answers_tenant_submission", "tenant_id", "submission_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    submission_id: Mapped[str] = mapped_column(ForeignKey("tenant_form_submissions.id"), nullable=False)
    field_id: Mapped[str | None] = mapped_column(ForeignKey("tenant_form_fields.id"), nullable=True)
    field_key: Mapped[str] = mapped_column(String(80), nullable=False)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    tenant = relationship("Tenant")
    submission = relationship("TenantFormSubmission", back_populates="answers")
    field = relationship("TenantFormField")


class TenantVoiceProviderConfig(Base, TimestampMixin):
    __tablename__ = "tenant_voice_provider_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", name="uq_tenant_voice_provider_configs_tenant_provider"),
        Index("ix_tenant_voice_provider_configs_tenant_provider", "tenant_id", "provider"),
        Index("ix_tenant_voice_provider_configs_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="ultravox")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="inactive")
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_voice_agent_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    default_from_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    default_language: Mapped[str] = mapped_column(String(16), nullable=False, default="es")
    default_timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="America/Bogota")
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant = relationship("Tenant")


class TenantSipRoute(Base, TimestampMixin):
    __tablename__ = "tenant_sip_routes"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_tenant_sip_routes_tenant"),
        UniqueConstraint("provider_config_id", name="uq_tenant_sip_routes_provider_config"),
        UniqueConstraint("sip_username", name="uq_tenant_sip_routes_sip_username"),
        Index("ix_tenant_sip_routes_tenant_status", "tenant_id", "status"),
        sa.CheckConstraint("status IN ('active','inactive')", name="ck_tenant_sip_routes_status"),
        sa.CheckConstraint(
            "provision_status IN ('pending','active','failed','disabled')",
            name="ck_tenant_sip_routes_provision_status",
        ),
        sa.CheckConstraint("pbx_port BETWEEN 1 AND 65535", name="ck_tenant_sip_routes_port"),
        sa.CheckConstraint(
            "max_concurrent_calls BETWEEN 1 AND 100",
            name="ck_tenant_sip_routes_concurrency",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    provider_config_id: Mapped[str] = mapped_column(
        ForeignKey("tenant_voice_provider_configs.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="inactive")
    pbx_host: Mapped[str] = mapped_column(String(255), nullable=False)
    pbx_port: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=5060)
    sip_username: Mapped[str] = mapped_column(String(120), nullable=False)
    sip_password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    caller_id: Mapped[str] = mapped_column(String(32), nullable=False)
    default_country: Mapped[str] = mapped_column(String(2), nullable=False, default="CO")
    allowed_countries_json: Mapped[list] = mapped_column(sa.JSON, nullable=False, default=list)
    max_concurrent_calls: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    provision_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="disabled"
    )
    desired_revision: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    applied_revision: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    provision_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    provisioned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_provision_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    tenant = relationship("Tenant")
    provider_config = relationship("TenantVoiceProviderConfig")


class TenantChatwootConfig(Base, TimestampMixin):
    __tablename__ = "tenant_chatwoot_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", name="uq_tenant_chatwoot_configs_tenant_provider"),
        UniqueConstraint("webhook_key", name="uq_tenant_chatwoot_configs_webhook_key"),
        # Aislamiento entre tenants: la misma Account de Chatwoot (identificada
        # por su instancia + account_id) no puede pertenecer a mas de un
        # tenant. account_id solo no alcanza porque dos instancias Chatwoot
        # distintas pueden reusar el mismo account_id.
        UniqueConstraint("base_url", "account_id", name="uq_tenant_chatwoot_configs_base_url_account_id"),
        Index("ix_tenant_chatwoot_configs_tenant_provider", "tenant_id", "provider"),
        Index("ix_tenant_chatwoot_configs_tenant_status", "tenant_id", "status"),
        Index("ix_tenant_chatwoot_configs_account_id", "account_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="chatwoot")
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="external")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="inactive")
    base_url: Mapped[str] = mapped_column(String(255), nullable=False, default="https://crm.serviglobal-ia.com")
    account_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    account_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    default_inbox_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    default_inbox_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    api_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_key: Mapped[str] = mapped_column(String(64), nullable=False)
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant = relationship("Tenant")


class TenantChatwootInbox(Base, TimestampMixin):
    __tablename__ = "tenant_chatwoot_inboxes"
    __table_args__ = (
        Index("ix_tenant_chatwoot_inboxes_tenant_config", "tenant_id", "chatwoot_config_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    chatwoot_config_id: Mapped[str] = mapped_column(ForeignKey("tenant_chatwoot_configs.id"), nullable=False)
    chatwoot_inbox_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    channel: Mapped[str | None] = mapped_column(String(80), nullable=True)
    name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    is_default: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)

    tenant = relationship("Tenant")
    chatwoot_config = relationship("TenantChatwootConfig")


class TenantVoiceAgentConfig(Base, TimestampMixin):
    __tablename__ = "tenant_voice_agent_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider_agent_id", name="uq_tenant_voice_agent_configs_tenant_agent"),
        Index("ix_tenant_voice_agent_configs_tenant_agent", "tenant_id", "provider_agent_id"),
        Index("ix_tenant_voice_agent_configs_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    provider_config_id: Mapped[str | None] = mapped_column(ForeignKey("tenant_voice_provider_configs.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="ultravox")
    provider_agent_id: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    purpose: Mapped[str] = mapped_column(String(80), nullable=False, default="Atención al Cliente")
    default_language: Mapped[str] = mapped_column(String(16), nullable=False, default="es")
    default_timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="America/Bogota")
    default_voice: Mapped[str | None] = mapped_column(String(80), nullable=True)
    default_system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_tools_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    handoff_enabled: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    handoff_chatwoot_inbox_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    handoff_chatwoot_team_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    handoff_triggers: Mapped[list] = mapped_column(sa.JSON, nullable=False, default=list)
    handoff_lead_score_threshold: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=80)

    tenant = relationship("Tenant")
    provider_config = relationship("TenantVoiceProviderConfig")
