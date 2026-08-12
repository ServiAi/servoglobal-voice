from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.identity import _utcnow, _uuid


class TenantVoiceExperienceSubmission(Base):
    __tablename__ = "tenant_voice_experience_submissions"
    __table_args__ = (
        Index("ix_voice_submissions_tenant_created", "tenant_id", "created_at"),
        Index("ix_voice_submissions_experience", "experience_id"),
        sa.CheckConstraint("locale IN ('es', 'en')", name="ck_voice_submissions_locale"),
        sa.CheckConstraint(
            "(consent_accepted = true AND consent_accepted_at IS NOT NULL) OR "
            "(consent_accepted = false AND consent_accepted_at IS NULL)",
            name="ck_voice_submissions_consent_evidence",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    experience_id: Mapped[str] = mapped_column(
        ForeignKey("tenant_voice_experiences.id"), nullable=False
    )
    experience_version_id: Mapped[str] = mapped_column(
        ForeignKey("tenant_voice_experience_versions.id"), nullable=False
    )
    context_schema_id: Mapped[str] = mapped_column(
        ForeignKey("tenant_voice_context_schemas.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    locale: Mapped[str] = mapped_column(String(8), nullable=False)
    crm_contact_id: Mapped[str | None] = mapped_column(
        ForeignKey("crm_contacts.id", ondelete="SET NULL"), nullable=True
    )
    crm_lead_id: Mapped[str | None] = mapped_column(
        ForeignKey("crm_leads.id", ondelete="SET NULL"), nullable=True
    )
    consent_accepted: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    consent_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    values: Mapped[list["TenantVoiceExperienceSubmissionValue"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )


class TenantVoiceExperienceSubmissionValue(Base):
    __tablename__ = "tenant_voice_experience_submission_values"
    __table_args__ = (
        UniqueConstraint(
            "submission_id", "field_key", name="uq_voice_submission_values_field"
        ),
        Index("ix_voice_submission_values_submission", "submission_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("tenant_voice_experience_submissions.id", ondelete="CASCADE"),
        nullable=False,
    )
    field_key: Mapped[str] = mapped_column(String(80), nullable=False)
    field_type: Mapped[str] = mapped_column(String(20), nullable=False)
    value_json: Mapped[object] = mapped_column(sa.JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    submission: Mapped[TenantVoiceExperienceSubmission] = relationship(
        back_populates="values"
    )


class TenantVoiceContextSession(Base):
    __tablename__ = "tenant_voice_context_sessions"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_voice_context_sessions_token_hash"),
        UniqueConstraint("submission_id", name="uq_voice_context_sessions_submission"),
        Index("ix_voice_context_sessions_tenant_expires", "tenant_id", "expires_at"),
        sa.CheckConstraint(
            "status IN ('active', 'consumed', 'expired')",
            name="ck_voice_context_sessions_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("tenant_voice_experience_submissions.id", ondelete="CASCADE"),
        nullable=False,
    )
    experience_id: Mapped[str] = mapped_column(
        ForeignKey("tenant_voice_experiences.id"), nullable=False
    )
    experience_version_id: Mapped[str] = mapped_column(
        ForeignKey("tenant_voice_experience_versions.id"), nullable=False
    )
    context_schema_id: Mapped[str] = mapped_column(
        ForeignKey("tenant_voice_context_schemas.id"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    def mark_consumed(self, db, *, now: datetime | None = None) -> bool:
        current = now or datetime.now(UTC)
        consumed = db.query(type(self)).filter(
            type(self).id == self.id,
            type(self).status == "active",
            type(self).expires_at > current,
        ).update(
            {type(self).status: "consumed", type(self).consumed_at: current},
            synchronize_session=False,
        )
        if not consumed:
            db.query(type(self)).filter(
                type(self).id == self.id,
                type(self).status == "active",
                type(self).expires_at <= current,
            ).update({type(self).status: "expired"}, synchronize_session=False)
        db.commit()
        db.refresh(self)
        return consumed == 1


class VoicePublicRateLimitWindow(Base):
    __tablename__ = "voice_public_rate_limit_windows"
    __table_args__ = (
        UniqueConstraint("scope", "window_start", name="uq_voice_rate_windows_scope_start"),
        Index("ix_voice_rate_windows_window_start", "window_start"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    scope: Mapped[str] = mapped_column(String(160), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
