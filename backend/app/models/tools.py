from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.identity import TimestampMixin, _uuid


class TenantTool(Base, TimestampMixin):
    """A tenant-authored Custom HTTP Tool identity row.

    Distinct from `app.domain.tool_registry.ToolDefinition` (the static,
    code-defined Platform Tool catalog): this table is the DB-backed
    per-tenant catalog for tools under the reserved `custom.*` namespace
    (see app.domain.tool_namespace). A tool starts `disabled` and must be
    explicitly activated once its HTTP config (and credential, if any) is in
    place.
    """

    __tablename__ = "tenant_tools"
    __table_args__ = (
        UniqueConstraint("tenant_id", "key", name="uq_tenant_tools_tenant_key"),
        Index("ix_tenant_tools_tenant_id", "tenant_id"),
        Index("ix_tenant_tools_tenant_status", "tenant_id", "status"),
        sa.CheckConstraint("key LIKE 'custom.%'", name="ck_tenant_tools_key_namespace"),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_tenant_tools_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(90), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="disabled")
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    tenant = relationship("Tenant")
    created_by_user = relationship("User")
    http_config: Mapped[TenantHttpToolConfig | None] = relationship(
        back_populates="tenant_tool",
        cascade="all, delete-orphan",
        uselist=False,
    )
    credential: Mapped[TenantToolCredential | None] = relationship(
        back_populates="tenant_tool",
        cascade="all, delete-orphan",
        uselist=False,
    )


class TenantHttpToolConfig(Base, TimestampMixin):
    """Declarative HTTP execution config for a TenantTool. Never holds secrets."""

    __tablename__ = "tenant_http_tool_configs"
    __table_args__ = (
        UniqueConstraint("tenant_tool_id", name="uq_tenant_http_tool_configs_tenant_tool"),
        Index("ix_tenant_http_tool_configs_tenant_tool", "tenant_id", "tenant_tool_id"),
        sa.CheckConstraint(
            "method IN ('GET', 'POST', 'PUT', 'PATCH', 'DELETE')",
            name="ck_tenant_http_tool_configs_method",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    tenant_tool_id: Mapped[str] = mapped_column(
        ForeignKey("tenant_tools.id", ondelete="CASCADE"), nullable=False
    )
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    path_template: Mapped[str] = mapped_column(String(1024), nullable=False, default="/")
    timeout_ms: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=8000)
    headers_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    path_mapping_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    query_mapping_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    body_mapping_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    input_schema_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    response_mapping_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)

    tenant = relationship("Tenant")
    tenant_tool: Mapped[TenantTool] = relationship(
        back_populates="http_config", foreign_keys=[tenant_tool_id]
    )


class TenantToolCredential(Base, TimestampMixin):
    """Encrypted auth material for a TenantTool, kept in its own table so a
    bug in the config serializer can never accidentally leak a secret.
    """

    __tablename__ = "tenant_tool_credentials"
    __table_args__ = (
        UniqueConstraint("tenant_tool_id", name="uq_tenant_tool_credentials_tenant_tool"),
        Index("ix_tenant_tool_credentials_tenant_tool", "tenant_id", "tenant_tool_id"),
        sa.CheckConstraint(
            "auth_type IN ('none', 'bearer', 'api_key', 'basic')",
            name="ck_tenant_tool_credentials_auth_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    tenant_tool_id: Mapped[str] = mapped_column(
        ForeignKey("tenant_tools.id", ondelete="CASCADE"), nullable=False
    )
    auth_type: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    api_key_header_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    secrets_json_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rotated_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    tenant = relationship("Tenant")
    tenant_tool: Mapped[TenantTool] = relationship(
        back_populates="credential", foreign_keys=[tenant_tool_id]
    )
    rotated_by_user = relationship("User", foreign_keys=[rotated_by_user_id])
