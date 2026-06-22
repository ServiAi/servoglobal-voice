from __future__ import annotations

import sqlalchemy as sa
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.identity import TimestampMixin, _uuid, _utcnow

class CrmContact(Base, TimestampMixin):
    __tablename__ = "crm_contacts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "phone_normalized", name="uq_crm_contacts_tenant_phone"),
        Index("ix_crm_contacts_tenant_id", "tenant_id"),
        Index("ix_crm_contacts_phone_normalized", "phone_normalized"),
        Index("ix_crm_contacts_email", "email"),
        sa.Index(
            "ix_crm_contacts_tenant_email_uniq",
            "tenant_id",
            "email",
            unique=True,
            postgresql_where=sa.text("email IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Lead sin nombre")
    phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    phone_normalized: Mapped[str | None] = mapped_column(String(80), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    metadata_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)

    tenant = relationship("Tenant")
    leads: Mapped[list[CrmLead]] = relationship(back_populates="contact", cascade="all, delete-orphan")
    activities: Mapped[list[CrmActivity]] = relationship(back_populates="contact", cascade="all, delete-orphan")
    tasks: Mapped[list[CrmTask]] = relationship(back_populates="contact", cascade="all, delete-orphan")


class CrmPipelineStage(Base, TimestampMixin):
    __tablename__ = "crm_pipeline_stages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "key", name="uq_crm_pipeline_stages_tenant_key"),
        Index("ix_crm_pipeline_stages_tenant_key", "tenant_id", "key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_terminal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    tenant = relationship("Tenant")
    leads: Mapped[list[CrmLead]] = relationship(back_populates="stage")


class CrmLead(Base, TimestampMixin):
    __tablename__ = "crm_leads"
    __table_args__ = (
        Index("ix_crm_leads_tenant_contact_status", "tenant_id", "contact_id", "status"),
        Index("ix_crm_leads_tenant_last_call", "tenant_id", "last_call_id"),
        Index(
            "ix_crm_leads_tenant_created_call_unique",
            "tenant_id",
            "created_from_call_id",
            unique=True,
            postgresql_where=sa.text("created_from_call_id IS NOT NULL"),
            sqlite_where=sa.text("created_from_call_id IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    contact_id: Mapped[str] = mapped_column(ForeignKey("crm_contacts.id"), nullable=False)
    current_stage_id: Mapped[str] = mapped_column(ForeignKey("crm_pipeline_stages.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    lead_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interest: Mapped[str | None] = mapped_column(String(255), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    use_case: Mapped[str | None] = mapped_column(String(255), nullable=True)
    volume: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pain_point: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget_range: Mapped[str | None] = mapped_column(String(255), nullable=True)
    intent_level: Mapped[str | None] = mapped_column(String(80), nullable=True)
    next_action: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    created_from_call_id: Mapped[str | None] = mapped_column(ForeignKey("calls.id"), nullable=True)
    last_call_id: Mapped[str | None] = mapped_column(ForeignKey("calls.id"), nullable=True)
    short_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    campaign: Mapped[str | None] = mapped_column(String(120), nullable=True)

    tenant = relationship("Tenant")
    contact: Mapped[CrmContact] = relationship(back_populates="leads")
    stage: Mapped[CrmPipelineStage] = relationship(back_populates="leads")
    owner_agent = relationship("Agent")
    created_from_call = relationship("Call", foreign_keys=[created_from_call_id])
    last_call = relationship("Call", foreign_keys=[last_call_id])
    activities: Mapped[list[CrmActivity]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    tasks: Mapped[list[CrmTask]] = relationship(back_populates="lead", cascade="all, delete-orphan")


class CrmCallContext(Base, TimestampMixin):
    __tablename__ = "crm_call_contexts"
    __table_args__ = (
        Index("ix_crm_call_contexts_tenant_provider_call", "tenant_id", "external_provider", "external_call_id"),
        Index("ix_crm_call_contexts_tenant_form_submission", "tenant_id", "form_submission_id"),
        Index("ix_crm_call_contexts_tenant_context", "tenant_id", "context_id"),
        Index("ix_crm_call_contexts_tenant_phone", "tenant_id", "phone_normalized"),
        Index("ix_crm_call_contexts_tenant_created_at", "tenant_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    external_provider: Mapped[str] = mapped_column(String(80), nullable=False)
    external_call_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    form_submission_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    context_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    phone_normalized: Mapped[str | None] = mapped_column(String(80), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    interest: Mapped[str | None] = mapped_column(String(255), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    use_case: Mapped[str | None] = mapped_column(String(255), nullable=True)
    volume: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pain_point: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget_range: Mapped[str | None] = mapped_column(String(255), nullable=True)
    intent_level: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    campaign: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(120), nullable=True)
    raw_context_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")

    tenant = relationship("Tenant")


class CrmActivity(Base):
    __tablename__ = "crm_activities"
    __table_args__ = (
        UniqueConstraint("tenant_id", "call_id", "activity_type", "deduplication_key", name="uq_crm_activities_tenant_call_type_dedup"),
        Index("ix_crm_activities_tenant_call_type_dedup", "tenant_id", "call_id", "activity_type", "deduplication_key"),
        Index("ix_crm_activities_tenant_contact", "tenant_id", "contact_id"),
        Index("ix_crm_activities_occurred_at", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("crm_leads.id"), nullable=True)
    contact_id: Mapped[str] = mapped_column(ForeignKey("crm_contacts.id"), nullable=False)
    call_id: Mapped[str | None] = mapped_column(ForeignKey("calls.id"), nullable=True)
    activity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    payload_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # Stage history & deduplication columns
    from_stage_id: Mapped[str | None] = mapped_column(ForeignKey("crm_pipeline_stages.id"), nullable=True)
    to_stage_id: Mapped[str | None] = mapped_column(ForeignKey("crm_pipeline_stages.id"), nullable=True)
    deduplication_key: Mapped[str] = mapped_column(String(120), nullable=False, default="")

    tenant = relationship("Tenant")
    contact: Mapped[CrmContact] = relationship(back_populates="activities")
    lead: Mapped[CrmLead | None] = relationship(back_populates="activities")
    call = relationship("Call")

    # Stage history relationships
    from_stage = relationship("CrmPipelineStage", foreign_keys=[from_stage_id])
    to_stage = relationship("CrmPipelineStage", foreign_keys=[to_stage_id])


class CrmTask(Base, TimestampMixin):
    __tablename__ = "crm_tasks"
    __table_args__ = (
        Index("ix_crm_tasks_tenant_lead", "tenant_id", "lead_id"),
        Index("ix_crm_tasks_due_at", "due_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("crm_leads.id"), nullable=True)
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("crm_contacts.id"), nullable=True)
    assigned_to_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    priority: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")

    tenant = relationship("Tenant")
    contact: Mapped[CrmContact | None] = relationship(back_populates="tasks")
    lead: Mapped[CrmLead | None] = relationship(back_populates="tasks")
    assigned_to = relationship("User")
