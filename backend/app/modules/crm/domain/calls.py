"""Pure DTOs describing a call as CRM sees it. Frozen, ORM-free: other modules
(Analytics, Voice Legacy) hand these to CRM; CRM never reads their rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CallRef:
    """The fields of a (provider) call that CRM ingestion needs."""

    id: str | None
    tenant_id: str | None
    external_provider: str | None = None
    external_call_id: str | None = None
    customer_phone: str | None = None
    normalized_status: str | None = None
    provider_status: str | None = None
    joined_at: datetime | None = None
    summary: str | None = None
    short_summary: str | None = None
    duration_seconds: int | None = None
    billed_minutes: float | None = None


@dataclass(frozen=True)
class BookingDetection:
    created: bool
    event_id: str | None = None
    start_time: str | None = None


@dataclass(frozen=True)
class CallClassification:
    stage_key: str | None
    next_action: str | None = None


@dataclass(frozen=True)
class ContextLookup:
    """Identifiers a provider payload carries that locate a CRM call context."""

    external_call_id: str | None = None
    form_submission_id: str | None = None
    context_id: str | None = None
    phone: str | None = None
