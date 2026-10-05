from __future__ import annotations

import sqlalchemy as sa
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, _utcnow, _uuid


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="America/Bogota")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    memberships: Mapped[list[TenantMembership]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list[AccessAuditLog]] = relationship(back_populates="tenant")


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "ix_users_email_partial_unique",
            "email",
            unique=True,
            postgresql_where=sa.text("status != 'deleted'"),
        ),
        Index(
            "ix_users_external_auth_id_partial_unique",
            "external_auth_id",
            unique=True,
            postgresql_where=sa.text("external_auth_id IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    external_auth_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_internal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    memberships: Mapped[list[TenantMembership]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list[AccessAuditLog]] = relationship(back_populates="user")


class TenantMembership(Base, TimestampMixin):
    __tablename__ = "tenant_memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_memberships_tenant_user"),
        Index("ix_tenant_memberships_tenant_id", "tenant_id"),
        Index("ix_tenant_memberships_user_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    tenant: Mapped[Tenant] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


class AccessAuditLog(Base):
    __tablename__ = "access_audit_logs"
    __table_args__ = (
        Index("ix_access_audit_logs_user_id", "user_id"),
        Index("ix_access_audit_logs_tenant_id", "tenant_id"),
        Index("ix_access_audit_logs_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    resource: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    user: Mapped[User | None] = relationship(back_populates="audit_logs")
    tenant: Mapped[Tenant | None] = relationship(back_populates="audit_logs")

from sqlalchemy import Index as _FeatureGrantIndex, UniqueConstraint as _FeatureGrantUniqueConstraint
from sqlalchemy.orm import relationship as _feature_grant_relationship


class TenantFeatureGrant(Base, TimestampMixin):
    __tablename__ = "tenant_feature_grants"
    __table_args__ = (
        _FeatureGrantUniqueConstraint(
            "tenant_id", "feature_key", name="uq_tenant_feature_grants_tenant_feature_key"
        ),
        _FeatureGrantIndex("ix_tenant_feature_grants_tenant_id", "tenant_id"),
        _FeatureGrantIndex("ix_tenant_feature_grants_feature_key", "feature_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    feature_key: Mapped[str] = mapped_column(String(80), nullable=False)
    enabled: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    limits_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    enabled_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    tenant = _feature_grant_relationship("Tenant")
