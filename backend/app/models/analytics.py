from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


NORMALIZED_CALL_STATUSES = (
    "in_progress",
    "answered",
    "unanswered",
    "rejected",
    "failed",
    "cancelled",
    "transferred",
    "voicemail",
)


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class Agent(Base, TimestampMixin):
    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "external_provider",
            "external_agent_id",
            name="uq_agents_tenant_provider_external_agent",
        ),
        Index("ix_agents_tenant_id", "tenant_id"),
        Index("ix_agents_external_agent_id", "external_agent_id"),
        Index("ix_agents_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    external_provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    external_agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    channel_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    tenant = relationship("Tenant", back_populates="agents")
    calls: Mapped[list[Call]] = relationship(back_populates="agent")
    metric_snapshots: Mapped[list[MetricSnapshotDaily]] = relationship(back_populates="agent")


class Call(Base, TimestampMixin):
    __tablename__ = "calls"
    __table_args__ = (
        CheckConstraint(
            "normalized_status in ("
            "'in_progress', 'answered', 'unanswered', 'rejected', "
            "'failed', 'cancelled', 'transferred', 'voicemail'"
            ")",
            name="ck_calls_normalized_status",
        ),
        UniqueConstraint(
            "tenant_id",
            "external_provider",
            "external_call_id",
            name="uq_calls_tenant_provider_external_call",
        ),
        Index("ix_calls_tenant_id", "tenant_id"),
        Index("ix_calls_external_call_id", "external_call_id"),
        Index("ix_calls_started_at", "started_at"),
        Index("ix_calls_tenant_started_at", "tenant_id", "started_at"),
        Index("ix_calls_tenant_normalized_status", "tenant_id", "normalized_status"),
        Index("ix_calls_tenant_agent_id", "tenant_id", "agent_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    external_call_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_provider: Mapped[str] = mapped_column(String(80), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    provider_agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_status: Mapped[str | None] = mapped_column(String(120), nullable=True)
    normalized_status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    billed_minutes: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recording_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    direction: Mapped[str | None] = mapped_column(String(32), nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant", back_populates="calls")
    agent: Mapped[Agent | None] = relationship(back_populates="calls")
    events: Mapped[list[CallEvent]] = relationship(
        back_populates="call", cascade="all, delete-orphan"
    )


class CallEvent(Base):
    __tablename__ = "call_events"
    __table_args__ = (
        Index("ix_call_events_call_id", "call_id"),
        Index("ix_call_events_tenant_id", "tenant_id"),
        Index("ix_call_events_received_at", "received_at"),
        Index("ix_call_events_tenant_received_at", "tenant_id", "received_at"),
        UniqueConstraint("dedup_key", name="uq_call_events_dedup_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dedup_key: Mapped[str | None] = mapped_column(String(400), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="call_events")
    call: Mapped[Call] = relationship(back_populates="events")


class MetricSnapshotDaily(Base, TimestampMixin):
    __tablename__ = "metric_snapshots_daily"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "agent_id",
            "date",
            name="uq_metric_snapshots_daily_tenant_agent_date",
        ),
        Index("ix_metric_snapshots_daily_tenant_date", "tenant_id", "date"),
        Index("ix_metric_snapshots_daily_tenant_agent_date", "tenant_id", "agent_id", "date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    calls_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    calls_answered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    calls_unanswered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_total_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    billed_minutes: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)

    tenant = relationship("Tenant", back_populates="metric_snapshots")
    agent: Mapped[Agent | None] = relationship(back_populates="metric_snapshots")
