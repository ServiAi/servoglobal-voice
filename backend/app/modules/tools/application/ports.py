"""What Tool Platform needs from other modules to execute Platform Tools.

Structural Protocols: the other modules' public facades satisfy them
without inheriting from anything, and tests can pass plain fakes. The
dispatcher depends only on these; ``app.modules.tools.wiring`` is the one
place that binds them to the concrete facades.

Every cross-module entity is a frozen DTO from the owner's public API --
never an ORM row. ``Any`` remains only for genuinely dynamic payloads
(LLM-supplied ``notes``, provider availability results).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from app.modules.crm.public import ContactRef, LeadRef
from app.modules.voice.public import ToolSessionView


class BookingResult(Protocol):
    @property
    def id(self) -> str: ...
    @property
    def status(self) -> str: ...
    @property
    def start_at(self) -> datetime: ...


class SendResult(Protocol):
    @property
    def status(self) -> str: ...
    @property
    def provider_message_id(self) -> str | None: ...


class SchedulingToolPort(Protocol):
    def get_available_slots(self, *, tenant_id: str, date_input: str) -> dict[str, Any]: ...

    def create_lead_booking(
        self,
        *,
        tenant_id: str,
        lead_id: str,
        start: str,
        attendee_name: str,
        attendee_email: str,
        attendee_phone: str | None,
        notes: Any,
        idempotency_key: str | None = None,
    ) -> BookingResult: ...


class CrmToolPort(Protocol):
    def get_or_create_open_lead(
        self, *, tenant_id: str, phone: str, email: str | None, name: str
    ) -> tuple[ContactRef, LeadRef]: ...


class MessagingToolPort(Protocol):
    def send_template(
        self,
        *,
        tenant_id: str,
        to_phone: str,
        template_key: str,
        variables: dict[str, str],
        metadata: dict[str, Any],
        lead_id: str | None,
        contact_id: str | None,
    ) -> SendResult: ...


class VoiceSessionToolPort(Protocol):
    def get_tool_session(self, session_id: str) -> ToolSessionView: ...

    def record_event(self, session_id: str, event_type: str, *, source: str, payload: dict[str, Any]) -> None: ...

    def enrich_context(
        self, session_id: str, *, contact: ContactRef | None, lead: LeadRef | None, event_source: str
    ) -> None: ...


class ToolAuditPort(Protocol):
    def record(
        self,
        *,
        tenant_id: str,
        provider: str,
        event_type: str,
        status: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...


@dataclass(frozen=True)
class ToolPorts:
    scheduling: SchedulingToolPort
    crm: CrmToolPort
    messaging: MessagingToolPort
    sessions: VoiceSessionToolPort
    audit: ToolAuditPort
