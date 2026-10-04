"""Ports from CRM to the rest of the platform (bound in ``crm/wiring.py``).

CRM application code depends on these Protocols only: no Analytics, Identity,
Messaging, Email or Forms ORM and no provider payload shape crosses into it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from app.modules.crm.domain.calls import BookingDetection, CallClassification, CallRef, ContextLookup


class TaskAssigneePort(Protocol):
    def is_active_member(self, tenant_id: str, user_id: str) -> bool:
        """Is ``user_id`` an active member of the tenant? (Identity answers.)"""
        ...


class SchedulingPort(Protocol):
    def detach_customers(self, *, tenant_id: str, lead_ids: Sequence[str], contact_ids: Sequence[str]) -> None:
        """Keep the bookings, clear their now-dangling lead/contact ids."""
        ...


class LeadHistoryPort(Protocol):
    """Operational history owned by other modules (Messaging, Email, Forms)
    that references leads/contacts. Temporary legacy adapters until those
    modules expose their own ``public.py``."""

    def clear_references(self, *, tenant_id: str, lead_ids: Sequence[str], contact_ids: Sequence[str]) -> None:
        """Null the lead/contact ids of WhatsApp messages and email sends."""
        ...

    def delete_form_artifacts(self, *, tenant_id: str, lead_ids: Sequence[str]) -> None:
        """Form tokens/submissions need a lead and cannot outlive it."""
        ...


class AnalyticsPort(Protocol):
    def find_call_id(self, tenant_id: str, external_provider: str | None, external_call_id: str) -> str | None:
        """Analytics' own call id for a provider call, if it exists."""
        ...


class CallPayloadPort(Protocol):
    """Provider payload parsing (Voice Legacy adapter). CRM only sees the
    normalised results below."""

    def event_type(self, payload: Mapping[str, Any]) -> str: ...

    def context_lookup(self, payload: Mapping[str, Any]) -> ContextLookup: ...

    def extract_context(
        self, payload: Mapping[str, Any], call: CallRef | None, call_context: Mapping[str, Any] | None
    ) -> dict[str, Any]: ...

    def summary_fields(self, payload: Mapping[str, Any], call: CallRef) -> tuple[str | None, str | None]: ...

    def end_reason(self, payload: Mapping[str, Any], call: CallRef) -> str: ...

    def billed_duration(self, payload: Mapping[str, Any]) -> Any: ...

    def detect_booking(self, payload: Mapping[str, Any]) -> BookingDetection: ...

    def classify_after_call(
        self, call_status: str | None, summary: str | None, short_summary: str | None, payload: Mapping[str, Any]
    ) -> CallClassification: ...


@dataclass(frozen=True)
class CrmPorts:
    assignees: TaskAssigneePort
    scheduling: SchedulingPort
    history: LeadHistoryPort
    analytics: AnalyticsPort
    payloads: CallPayloadPort
