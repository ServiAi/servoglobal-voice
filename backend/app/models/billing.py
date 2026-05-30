from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class TenantBillingPlan(Base, TimestampMixin):
    __tablename__ = "tenant_billing_plans"
    __table_args__ = (
        CheckConstraint(
            "plan_key in ('web_conversion', 'voice_cloud_pbx', 'enterprise')",
            name="ck_tenant_billing_plans_plan_key",
        ),
        CheckConstraint("included_minutes >= 2000", name="ck_tenant_billing_plans_min_minutes"),
        CheckConstraint("price_per_minute_usd > 0", name="ck_tenant_billing_plans_positive_price"),
        CheckConstraint(
            "plan_key != 'web_conversion' OR price_per_minute_usd = 0.16",
            name="ck_tenant_billing_plans_web_price",
        ),
        CheckConstraint(
            "plan_key != 'voice_cloud_pbx' OR price_per_minute_usd = 0.18",
            name="ck_tenant_billing_plans_voice_price",
        ),
        CheckConstraint(
            "plan_key != 'enterprise' OR "
            "(price_per_minute_usd >= 0.14 AND price_per_minute_usd <= 0.15)",
            name="ck_tenant_billing_plans_enterprise_price",
        ),
        CheckConstraint(
            "usage_status in ("
            "'normal', 'approaching_limit', 'limit_reached', "
            "'over_limit', 'suspended_usage_limit'"
            ")",
            name="ck_tenant_billing_plans_usage_status",
        ),
        UniqueConstraint("tenant_id", name="uq_tenant_billing_plans_tenant_id"),
        Index("ix_tenant_billing_plans_tenant_id", "tenant_id"),
        Index("ix_tenant_billing_plans_usage_status", "usage_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    plan_key: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_name: Mapped[str] = mapped_column(String(120), nullable=False)
    included_minutes: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    price_per_minute_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    usage_status: Mapped[str] = mapped_column(String(32), nullable=False, default="normal")
    billing_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    billing_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    alert_thresholds: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=lambda: [80, 90, 100])
    last_usage_recalculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant", back_populates="billing_plan")
    alerts: Mapped[list[TenantUsageAlert]] = relationship(
        back_populates="billing_plan",
        cascade="all, delete-orphan",
    )


class TenantUsageAlert(Base, TimestampMixin):
    __tablename__ = "tenant_usage_alerts"
    __table_args__ = (
        CheckConstraint(
            "alert_type in ('warning_80', 'warning_90', 'limit_reached')",
            name="ck_tenant_usage_alerts_alert_type",
        ),
        UniqueConstraint(
            "tenant_id",
            "alert_type",
            "billing_period_start",
            name="uq_tenant_usage_alerts_tenant_type_period",
        ),
        Index("ix_tenant_usage_alerts_tenant_id", "tenant_id"),
        Index("ix_tenant_usage_alerts_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    billing_plan_id: Mapped[str] = mapped_column(ForeignKey("tenant_billing_plans.id"), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)
    threshold_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    billing_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    tenant = relationship("Tenant", back_populates="usage_alerts")
    billing_plan: Mapped[TenantBillingPlan] = relationship(back_populates="alerts")


class ExternalProviderPricing(Base, TimestampMixin):
    __tablename__ = "external_provider_pricing"
    __table_args__ = (
        UniqueConstraint("provider_key", name="uq_external_provider_pricing_key"),
        Index("ix_external_provider_pricing_provider_key", "provider_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    provider_key: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_price_per_minute_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    price_min_per_minute_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    price_max_per_minute_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    price_source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
