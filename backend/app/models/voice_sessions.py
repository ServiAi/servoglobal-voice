from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import event, inspect
from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.identity import TimestampMixin, _utcnow, _uuid


class VoiceSession(Base, TimestampMixin):
    __tablename__ = "voice_sessions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_voice_sessions_tenant_idempotency"),
        Index("ix_voice_sessions_tenant_status", "tenant_id", "status"),
        Index("ix_voice_sessions_agent", "agent_id"),
        Index("ix_voice_sessions_agent_version", "agent_version_id"),
        Index("ix_voice_sessions_created_at", "created_at"),
        sa.CheckConstraint(
            "status IN ('requested','dispatching','dispatched','starting','connected','ending','ended','failed','cancelled')",
            name="ck_voice_sessions_status",
        ),
        sa.CheckConstraint("channel IN ('web','sip','internal_test')", name="ck_voice_sessions_channel"),
        sa.CheckConstraint("direction IN ('inbound','outbound','internal')", name="ck_voice_sessions_direction"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(ForeignKey("tenant_agents.id"), nullable=False)
    agent_version_id: Mapped[str] = mapped_column(ForeignKey("tenant_agent_versions.id"), nullable=False)
    crm_voice_call_id: Mapped[str | None] = mapped_column(ForeignKey("crm_voice_calls.id", ondelete="SET NULL"), nullable=True)
    channel: Mapped[str] = mapped_column(String(24), nullable=False)
    direction: Mapped[str] = mapped_column(String(24), nullable=False)
    runtime_engine: Mapped[str] = mapped_column(String(32), nullable=False, default="livekit")
    pipeline_type: Mapped[str] = mapped_column(String(32), nullable=False, default="realtime")
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    livekit_room_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    livekit_dispatch_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    livekit_job_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="requested")
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message_sanitized: Mapped[str | None] = mapped_column(String(500), nullable=True)

    agent = relationship("TenantAgent", foreign_keys=[agent_id])
    agent_version = relationship("TenantAgentVersion", foreign_keys=[agent_version_id])
    events = relationship("VoiceSessionEvent", back_populates="voice_session", order_by="VoiceSessionEvent.created_at")


class VoiceSessionEvent(Base):
    __tablename__ = "voice_session_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_voice_session_events_event_id"),
        Index("ix_voice_session_events_tenant_session", "tenant_id", "voice_session_id"),
        Index("ix_voice_session_events_session_created", "voice_session_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(String(80), nullable=False, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    voice_session_id: Mapped[str] = mapped_column(ForeignKey("voice_sessions.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    sequence: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    payload_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    voice_session = relationship("VoiceSession", back_populates="events")


@event.listens_for(VoiceSession, "before_update")
def _keep_agent_version_immutable(_mapper, _connection, target: VoiceSession) -> None:
    if inspect(target).attrs.agent_version_id.history.has_changes():
        raise ValueError("VoiceSession.agent_version_id is immutable")
