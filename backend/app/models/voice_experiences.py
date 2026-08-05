from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.identity import TimestampMixin, _utcnow, _uuid


class TenantVoiceExperience(Base, TimestampMixin):
    __tablename__ = "tenant_voice_experiences"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_tenant_voice_experiences_slug"),
        Index("ix_tenant_voice_experiences_tenant_status", "tenant_id", "status"),
        Index("ix_tenant_voice_experiences_tenant_agent", "tenant_id", "agent_config_id"),
        Index("ix_tenant_voice_experiences_slug", "slug"),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'unpublished', 'archived')",
            name="ck_tenant_voice_experiences_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    agent_config_id: Mapped[str] = mapped_column(
        ForeignKey("tenant_voice_agent_configs.id"), nullable=False
    )
    context_schema_id: Mapped[str] = mapped_column(
        ForeignKey("tenant_voice_context_schemas.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    default_locale: Mapped[str] = mapped_column(String(16), nullable=False, default="es")
    content_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    theme_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    consent_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    call_settings_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    published_version_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "tenant_voice_experience_versions.id",
            name="fk_tenant_voice_experiences_published_version",
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
    agent_config = relationship("TenantVoiceAgentConfig")
    context_schema = relationship("TenantVoiceContextSchema")
    created_by_user = relationship("User")
    versions: Mapped[list[TenantVoiceExperienceVersion]] = relationship(
        back_populates="experience",
        cascade="all, delete-orphan",
        foreign_keys="TenantVoiceExperienceVersion.experience_id",
        order_by="TenantVoiceExperienceVersion.version",
    )
    published_version: Mapped[TenantVoiceExperienceVersion | None] = relationship(
        foreign_keys=[published_version_id],
        post_update=True,
    )


class TenantVoiceExperienceVersion(Base):
    __tablename__ = "tenant_voice_experience_versions"
    __table_args__ = (
        UniqueConstraint(
            "experience_id",
            "version",
            name="uq_tenant_voice_experience_versions_experience_version",
        ),
        Index("ix_tenant_voice_experience_versions_tenant", "tenant_id"),
        Index("ix_tenant_voice_experience_versions_experience", "experience_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    experience_id: Mapped[str] = mapped_column(
        ForeignKey("tenant_voice_experiences.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    agent_config_id: Mapped[str] = mapped_column(
        ForeignKey("tenant_voice_agent_configs.id"), nullable=False
    )
    context_schema_id: Mapped[str] = mapped_column(
        ForeignKey("tenant_voice_context_schemas.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    default_locale: Mapped[str] = mapped_column(String(16), nullable=False)
    content_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    theme_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    consent_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    call_settings_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    experience: Mapped[TenantVoiceExperience] = relationship(
        back_populates="versions", foreign_keys=[experience_id]
    )
    tenant = relationship("Tenant")
    agent_config = relationship("TenantVoiceAgentConfig")
    context_schema = relationship("TenantVoiceContextSchema")
    published_by_user = relationship("User")
