from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.identity import TimestampMixin, _utcnow, _uuid


class TenantAgent(Base, TimestampMixin):
    """Canonical ServiGlobal agent identity (provider-agnostic).

    This is deliberately separate from `app.models.analytics.Agent` (the
    per-call analytics mirror keyed by external_provider/external_agent_id)
    and from `TenantVoiceAgentConfig` (the legacy Ultravox-bound runtime
    config). `TenantAgent` + `TenantAgentVersion` are the new source of
    truth; the provider becomes an executor behind `runtime_binding_json`.
    """

    __tablename__ = "tenant_agents"
    __table_args__ = (
        Index("ix_tenant_agents_tenant_status", "tenant_id", "status"),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'archived')",
            name="ck_tenant_agents_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    published_version_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "tenant_agent_versions.id",
            name="fk_tenant_agents_published_version",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
    )
    draft_version_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "tenant_agent_versions.id",
            name="fk_tenant_agents_draft_version",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant")
    created_by_user = relationship("User")
    versions: Mapped[list[TenantAgentVersion]] = relationship(
        back_populates="agent",
        cascade="all, delete-orphan",
        foreign_keys="TenantAgentVersion.agent_id",
        order_by="TenantAgentVersion.version",
    )
    published_version: Mapped[TenantAgentVersion | None] = relationship(
        foreign_keys=[published_version_id],
        post_update=True,
    )
    draft_version: Mapped[TenantAgentVersion | None] = relationship(
        foreign_keys=[draft_version_id],
        post_update=True,
    )


class TenantAgentVersion(Base):
    __tablename__ = "tenant_agent_versions"
    __table_args__ = (
        UniqueConstraint("agent_id", "version", name="uq_tenant_agent_versions_agent_version"),
        Index("ix_tenant_agent_versions_tenant", "tenant_id"),
        Index("ix_tenant_agent_versions_agent", "agent_id"),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'superseded')",
            name="ck_tenant_agent_versions_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("tenant_agents.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="es")
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="America/Bogota")
    identity_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    instructions_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    behavior_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    runtime_binding_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    voice_agent_config_id: Mapped[str | None] = mapped_column(
        ForeignKey("tenant_voice_agent_configs.id", ondelete="SET NULL"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    agent: Mapped[TenantAgent] = relationship(back_populates="versions", foreign_keys=[agent_id])
    tenant = relationship("Tenant")
    voice_agent_config = relationship("TenantVoiceAgentConfig")
    created_by_user = relationship("User")
