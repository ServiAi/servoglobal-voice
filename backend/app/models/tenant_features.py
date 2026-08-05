from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.identity import TimestampMixin, _uuid


class TenantFeatureGrant(Base, TimestampMixin):
    __tablename__ = "tenant_feature_grants"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "feature_key",
            name="uq_tenant_feature_grants_tenant_feature_key",
        ),
        Index("ix_tenant_feature_grants_tenant_id", "tenant_id"),
        Index("ix_tenant_feature_grants_feature_key", "feature_key"),
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

    tenant = relationship("Tenant")
