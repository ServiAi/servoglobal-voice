"""What Voice Orchestration needs from other modules. ``wiring.py`` binds
these to the owners' public APIs; tests can pass plain fakes."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class ContactView(Protocol):
    @property
    def id(self) -> str: ...
    @property
    def tenant_id(self) -> str: ...
    @property
    def name(self) -> str | None: ...
    @property
    def phone(self) -> str | None: ...
    @property
    def email(self) -> str | None: ...


class LeadView(Protocol):
    @property
    def id(self) -> str: ...
    @property
    def tenant_id(self) -> str: ...
    @property
    def contact_id(self) -> str: ...
    @property
    def status(self) -> str: ...
    @property
    def stage_key(self) -> str | None: ...
    @property
    def campaign(self) -> str | None: ...


class CrmContextPort(Protocol):
    """Read-only CRM lookups used to build SessionContextV1. ``get_*`` are
    by id only: Voice compares ``tenant_id`` itself to fail closed."""

    def get_contact(self, contact_id: str) -> ContactView | None: ...

    def get_lead(self, lead_id: str) -> LeadView | None: ...

    def find_contact_by_normalized_phone(self, tenant_id: str, phone_normalized: str) -> ContactView | None: ...


class VoiceProjectionPort(Protocol):
    """Downstream projections of a session (call history, CRM call/activity).
    Voice owns the session facts; the projection owns what it writes."""

    def on_runtime_event(self, session_id: str, tenant_id: str, event_type: str, occurred_at: datetime | None) -> None:
        """Inside the caller's transaction (no commit)."""
        ...

    def reconcile(self, session_id: str, tenant_id: str) -> None:
        """Commits."""
        ...
