"""Immutable views CRM hands to other modules. No ORM rows, no SQLAlchemy.

Everything here is a frozen dataclass: callers read it, they cannot mutate CRM
state through it (mutations are explicit ``crm.public`` operations).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ContactRef:
    id: str
    tenant_id: str


@dataclass(frozen=True)
class LeadRef:
    id: str
    tenant_id: str
    contact_id: str
    status: str


@dataclass(frozen=True)
class ContactSnapshot:
    id: str
    tenant_id: str
    name: str | None
    phone: str | None
    email: str | None


@dataclass(frozen=True)
class LeadSnapshot:
    id: str
    tenant_id: str
    contact_id: str
    status: str
    stage_key: str | None
    campaign: str | None


@dataclass(frozen=True)
class ContactProfile:
    id: str
    tenant_id: str
    name: str | None
    phone: str | None
    phone_normalized: str | None
    email: str | None
    company: str | None
    source: str | None


@dataclass(frozen=True)
class LeadProfile:
    """A lead with the fields consumers render or branch on, plus its contact."""

    id: str
    tenant_id: str
    contact_id: str
    status: str
    stage_key: str | None
    stage_name: str | None
    lead_score: int | None
    interest: str | None
    industry: str | None
    use_case: str | None
    volume: str | None
    pain_point: str | None
    budget_range: str | None
    intent_level: str | None
    next_action: str | None
    summary: str | None
    short_summary: str | None
    source: str | None
    campaign: str | None
    context_id: str | None
    form_submission_id: str | None
    owner_agent_id: str | None
    created_from_call_id: str | None
    last_call_id: str | None
    contact: ContactProfile | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class ActivityView:
    id: str
    tenant_id: str
    lead_id: str | None
    contact_id: str
    call_id: str | None
    activity_type: str
    title: str
    description: str | None
    outcome: str | None
    occurred_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CallContextView:
    id: str
    tenant_id: str
    external_provider: str
    external_call_id: str | None
    form_submission_id: str | None
    context_id: str | None
    phone: str | None
    phone_normalized: str | None
    email: str | None
    name: str | None
    company: str | None
    interest: str | None
    industry: str | None
    use_case: str | None
    volume: str | None
    pain_point: str | None
    budget_range: str | None
    intent_level: str | None
    source: str | None
    campaign: str | None
    utm_source: str | None
    utm_campaign: str | None
    status: str
    created_at: datetime | None = None
    raw_context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VoiceCallView:
    id: str
    tenant_id: str
    lead_id: str | None
    contact_id: str | None
    source_submission_id: str | None
    sip_route_id: str | None
    provider: str
    provider_call_id: str | None
    provider_session_id: str | None
    provider_agent_id: str | None
    direction: str
    to_phone: str | None
    from_number: str | None
    status: str
    error_message: str | None
    recording_url: str | None
    transcript_url: str | None
    summary: str | None
    started_at: datetime | None
    provider_attempt_started_at: datetime | None
    answered_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True)
class OutboundContactRef:
    contact_id: str
    lead_id: str
    phone: str | None
    name: str | None
    company: str | None = None


@dataclass(frozen=True)
class CallState:
    status: str
    provider_call_id: str | None


@dataclass(frozen=True)
class FunnelBreakdown:
    name: str
    total: int
    qualified: int
    scheduled: int
    won: int


@dataclass(frozen=True)
class CrmFunnelSnapshot:
    """CRM-only dashboard numbers: leads per pipeline stage key, KPIs and
    source/campaign breakdowns."""

    stage_counts: dict[str, int]
    total_leads: int
    open_leads: int
    pending_tasks: int
    overdue_tasks: int
    leads_with_next_action: int
    sources: tuple[FunnelBreakdown, ...]
    campaigns: tuple[FunnelBreakdown, ...]


@dataclass(frozen=True)
class PendingActionCandidate:
    lead_id: str
    contact_name: str
    stage_key: str
    next_action: str | None
    source: str | None
    campaign: str | None
    updated_at: datetime
    last_call_id: str | None
    qualifies_without_call: bool
    requires_call_check: bool
