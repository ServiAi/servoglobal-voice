from __future__ import annotations

import sqlalchemy as sa
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.identity import TimestampMixin, _uuid, _utcnow


class TenantCapability(Base, TimestampMixin):
    __tablename__ = "tenant_capabilities"
    __table_args__ = (
        UniqueConstraint("tenant_id", "capability_key", name="uq_tenant_capabilities_tenant_capability_key"),
        Index("ix_tenant_capabilities_tenant_enabled", "tenant_id", "enabled"),
        Index("ix_tenant_capabilities_tenant_capability_key", "tenant_id", "capability_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    capability_key: Mapped[str] = mapped_column(String(80), nullable=False)
    enabled: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    config_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)

    tenant = relationship("Tenant")


class TenantNotificationRecipient(Base, TimestampMixin):
    __tablename__ = "tenant_notification_recipients"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "group_key",
            "channel",
            "destination",
            name="uq_tenant_notif_recipients_tenant_group_channel_dest",
        ),
        Index("ix_tenant_notification_recipients_tenant_group_status", "tenant_id", "group_key", "status"),
        Index("ix_tenant_notification_recipients_tenant_channel_status", "tenant_id", "channel", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    group_key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    metadata_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)

    tenant = relationship("Tenant")


class TenantNotificationRule(Base, TimestampMixin):
    __tablename__ = "tenant_notification_rules"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_tenant_notification_rules_tenant_name"),
        Index("ix_tenant_notification_rules_tenant_event_enabled", "tenant_id", "event_type", "enabled"),
        Index("ix_tenant_notification_rules_tenant_capability_enabled", "tenant_id", "capability_key", "enabled"),
        Index("ix_tenant_notification_rules_tenant_priority", "tenant_id", "priority"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    capability_key: Mapped[str] = mapped_column(String(80), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    action_type: Mapped[str] = mapped_column(String(80), nullable=False)
    template_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    recipient_strategy: Mapped[str] = mapped_column(String(40), nullable=False)
    recipient_group_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    conditions_json: Mapped[list] = mapped_column(sa.JSON, nullable=False, default=list)
    variable_mapping_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    schedule_mode: Mapped[str] = mapped_column(String(40), nullable=False, default="immediate")
    schedule_offset_minutes: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    priority: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=100)
    enabled: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)

    tenant = relationship("Tenant")


class DomainEvent(Base, TimestampMixin):
    __tablename__ = "domain_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_domain_events_tenant_idempotency_key"),
        Index("ix_domain_events_tenant_event_status", "tenant_id", "event_type", "status"),
        Index("ix_domain_events_status_available_at", "status", "available_at"),
        Index("ix_domain_events_tenant_resource", "tenant_id", "resource_type", "resource_id"),
        Index("ix_domain_events_tenant_correlation", "tenant_id", "correlation_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant = relationship("Tenant")
    deliveries: Mapped[list[NotificationDelivery]] = relationship(back_populates="domain_event")


class NotificationDelivery(Base, TimestampMixin):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_notification_deliveries_tenant_idempotency_key"),
        Index("ix_notification_deliveries_tenant_status_scheduled", "tenant_id", "status", "scheduled_for"),
        Index("ix_notification_deliveries_status_scheduled", "status", "scheduled_for"),
        Index("ix_notification_deliveries_tenant_provider_message", "tenant_id", "provider_message_id"),
        Index("ix_notification_deliveries_tenant_domain_event", "tenant_id", "domain_event_id"),
        Index("ix_notification_deliveries_tenant_rule", "tenant_id", "notification_rule_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    domain_event_id: Mapped[str] = mapped_column(ForeignKey("domain_events.id"), nullable=False)
    notification_rule_id: Mapped[str] = mapped_column(ForeignKey("tenant_notification_rules.id"), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    template_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    attempts: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)

    tenant = relationship("Tenant")
    domain_event: Mapped[DomainEvent] = relationship(back_populates="deliveries")
    notification_rule = relationship("TenantNotificationRule")
