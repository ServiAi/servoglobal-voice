"""Telephony persistence: the tenant's SIP route (PBX + LiveKit trunk).

Same table/columns/constraints as before the move (code ownership only; no
schema change). ``provider_config_id`` references tenant_voice_provider_configs,
which Voice Providers owns.
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, _uuid


class TenantSipRoute(Base, TimestampMixin):
    __tablename__ = "tenant_sip_routes"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_tenant_sip_routes_tenant"),
        UniqueConstraint("provider_config_id", name="uq_tenant_sip_routes_provider_config"),
        UniqueConstraint("livekit_outbound_trunk_id", name="uq_tenant_sip_routes_livekit_trunk"),
        UniqueConstraint("sip_username", name="uq_tenant_sip_routes_sip_username"),
        Index("ix_tenant_sip_routes_tenant_status", "tenant_id", "status"),
        sa.CheckConstraint("status IN ('active','inactive')", name="ck_tenant_sip_routes_status"),
        sa.CheckConstraint(
            "provision_status IN ('pending','active','failed','disabled')",
            name="ck_tenant_sip_routes_provision_status",
        ),
        sa.CheckConstraint(
            "livekit_provision_status IN ('pending','active','failed','disabled')",
            name="ck_tenant_sip_routes_livekit_provision_status",
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
    provider_config_id: Mapped[str | None] = mapped_column(
        ForeignKey("tenant_voice_provider_configs.id", ondelete="SET NULL"), nullable=True
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
    livekit_outbound_trunk_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    livekit_provision_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="disabled"
    )
    livekit_provision_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    livekit_provisioned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # No ORM relationships: provider_config_id is a plain FK to a table owned
    # by Voice Providers (checked through ProviderConfigRef), and the tenant
    # is a shared-kernel FK.
