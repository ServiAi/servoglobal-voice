"""Residual legacy models: Forms and Voice provider/agent config.

Integrations/Messaging tables live in app.modules.integrations.infrastructure.models.
These 7 tables are leftovers for future Forms / Voice-config modules.
"""

from __future__ import annotations

import sqlalchemy as sa
from datetime import date, datetime
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, _uuid, _utcnow


class TenantForm(Base, TimestampMixin):
    __tablename__ = "tenant_forms"
    __table_args__ = (
        Index("ix_tenant_forms_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    tenant = relationship("Tenant")
    fields: Mapped[list[TenantFormField]] = relationship(
        back_populates="form",
        cascade="all, delete-orphan",
        order_by="TenantFormField.position",
    )


class TenantFormField(Base, TimestampMixin):
    __tablename__ = "tenant_form_fields"
    __table_args__ = (
        Index("ix_tenant_form_fields_tenant_form", "tenant_id", "form_id"),
        UniqueConstraint("form_id", "key", name="uq_tenant_form_fields_form_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    form_id: Mapped[str] = mapped_column(ForeignKey("tenant_forms.id"), nullable=False)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    field_type: Mapped[str] = mapped_column(String(32), nullable=False)
    required: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    options_json: Mapped[list] = mapped_column(sa.JSON, nullable=False, default=list)
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    tenant = relationship("Tenant")
    form = relationship("TenantForm", back_populates="fields")


class TenantFormToken(Base):
    __tablename__ = "tenant_form_tokens"
    __table_args__ = (
        Index("ix_tenant_form_tokens_token_hash", "token_hash"),
        Index("ix_tenant_form_tokens_tenant_lead", "tenant_id", "lead_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    form_id: Mapped[str] = mapped_column(ForeignKey("tenant_forms.id"), nullable=False)
    lead_id: Mapped[str] = mapped_column(ForeignKey("crm_leads.id"), nullable=False)
    contact_id: Mapped[str] = mapped_column(ForeignKey("crm_contacts.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    tenant = relationship("Tenant")
    form = relationship("TenantForm")
    lead = relationship("CrmLead")
    contact = relationship("CrmContact")


class TenantFormSubmission(Base):
    __tablename__ = "tenant_form_submissions"
    __table_args__ = (
        Index("ix_tenant_form_submissions_tenant_lead", "tenant_id", "lead_id"),
        Index("ix_tenant_form_submissions_token", "token_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    form_id: Mapped[str] = mapped_column(ForeignKey("tenant_forms.id"), nullable=False)
    lead_id: Mapped[str] = mapped_column(ForeignKey("crm_leads.id"), nullable=False)
    contact_id: Mapped[str] = mapped_column(ForeignKey("crm_contacts.id"), nullable=False)
    token_id: Mapped[str] = mapped_column(ForeignKey("tenant_form_tokens.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="submitted")
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    tenant = relationship("Tenant")
    form = relationship("TenantForm")
    lead = relationship("CrmLead")
    contact = relationship("CrmContact")
    token = relationship("TenantFormToken")
    answers: Mapped[list[TenantFormSubmissionAnswer]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
    )


class TenantFormSubmissionAnswer(Base):
    __tablename__ = "tenant_form_submission_answers"
    __table_args__ = (
        Index("ix_tenant_form_submission_answers_tenant_submission", "tenant_id", "submission_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    submission_id: Mapped[str] = mapped_column(ForeignKey("tenant_form_submissions.id"), nullable=False)
    field_id: Mapped[str | None] = mapped_column(ForeignKey("tenant_form_fields.id"), nullable=True)
    field_key: Mapped[str] = mapped_column(String(80), nullable=False)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    tenant = relationship("Tenant")
    submission = relationship("TenantFormSubmission", back_populates="answers")
    field = relationship("TenantFormField")


class TenantVoiceProviderConfig(Base, TimestampMixin):
    __tablename__ = "tenant_voice_provider_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", name="uq_tenant_voice_provider_configs_tenant_provider"),
        Index("ix_tenant_voice_provider_configs_tenant_provider", "tenant_id", "provider"),
        Index("ix_tenant_voice_provider_configs_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="ultravox")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="inactive")
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_voice_agent_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    default_from_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    default_language: Mapped[str] = mapped_column(String(16), nullable=False, default="es")
    default_timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="America/Bogota")
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant = relationship("Tenant")


class TenantVoiceAgentConfig(Base, TimestampMixin):
    __tablename__ = "tenant_voice_agent_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider_agent_id", name="uq_tenant_voice_agent_configs_tenant_agent"),
        Index("ix_tenant_voice_agent_configs_tenant_agent", "tenant_id", "provider_agent_id"),
        Index("ix_tenant_voice_agent_configs_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    provider_config_id: Mapped[str | None] = mapped_column(ForeignKey("tenant_voice_provider_configs.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="ultravox")
    provider_agent_id: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    purpose: Mapped[str] = mapped_column(String(80), nullable=False, default="Atención al Cliente")
    default_language: Mapped[str] = mapped_column(String(16), nullable=False, default="es")
    default_timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="America/Bogota")
    default_voice: Mapped[str | None] = mapped_column(String(80), nullable=True)
    default_system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_tools_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    handoff_enabled: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    handoff_chatwoot_inbox_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    handoff_chatwoot_team_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    handoff_triggers: Mapped[list] = mapped_column(sa.JSON, nullable=False, default=list)
    handoff_lead_score_threshold: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=80)

    tenant = relationship("Tenant")
    provider_config = relationship("TenantVoiceProviderConfig")
