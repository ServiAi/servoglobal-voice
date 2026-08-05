from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.identity import TimestampMixin, _uuid


class TenantVoiceContextSchema(Base, TimestampMixin):
    __tablename__ = "tenant_voice_context_schemas"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "agent_config_id",
            "schema_key",
            "version",
            name="uq_tenant_voice_context_schemas_lineage_version",
        ),
        Index("ix_tenant_voice_context_schemas_tenant_agent", "tenant_id", "agent_config_id"),
        Index("ix_tenant_voice_context_schemas_tenant_key", "tenant_id", "schema_key"),
        Index("ix_tenant_voice_context_schemas_tenant_status", "tenant_id", "status"),
        Index(
            "uq_tenant_voice_context_schemas_active_lineage",
            "tenant_id",
            "agent_config_id",
            "schema_key",
            unique=True,
            postgresql_where=sa.text("status = 'active'"),
            sqlite_where=sa.text("status = 'active'"),
        ),
        Index(
            "uq_tenant_voice_context_schemas_draft_lineage",
            "tenant_id",
            "agent_config_id",
            "schema_key",
            unique=True,
            postgresql_where=sa.text("status = 'draft'"),
            sqlite_where=sa.text("status = 'draft'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    agent_config_id: Mapped[str] = mapped_column(
        ForeignKey("tenant_voice_agent_configs.id", ondelete="CASCADE"), nullable=False
    )
    schema_key: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant")
    agent_config = relationship("TenantVoiceAgentConfig")
    created_by_user = relationship("User")
    fields: Mapped[list["TenantVoiceContextField"]] = relationship(
        back_populates="schema",
        cascade="all, delete-orphan",
        order_by="TenantVoiceContextField.position",
    )


class TenantVoiceContextField(Base, TimestampMixin):
    __tablename__ = "tenant_voice_context_fields"
    __table_args__ = (
        UniqueConstraint(
            "schema_id",
            "key",
            name="uq_tenant_voice_context_fields_schema_key",
        ),
        UniqueConstraint(
            "schema_id",
            "position",
            name="uq_tenant_voice_context_fields_schema_position",
        ),
        Index("ix_tenant_voice_context_fields_tenant_schema", "tenant_id", "schema_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    schema_id: Mapped[str] = mapped_column(
        ForeignKey("tenant_voice_context_schemas.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    field_type: Mapped[str] = mapped_column(String(20), nullable=False)
    collection_mode: Mapped[str] = mapped_column(String(24), nullable=False)
    required: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    sensitivity: Mapped[str] = mapped_column(String(16), nullable=False, default="standard")
    validation_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    options_json: Mapped[list] = mapped_column(sa.JSON, nullable=False, default=list)

    tenant = relationship("Tenant")
    schema = relationship("TenantVoiceContextSchema", back_populates="fields")
