"""What Tool Platform needs from other modules to execute Platform Tools.

Structural Protocols: the other modules' public facades satisfy them
without inheriting from anything, and tests can pass plain fakes. The
dispatcher depends only on these; ``app.modules.tools.wiring`` is the one
place that binds them to the concrete facades.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


class BookingResult(Protocol):
    id: str
    status: str
    start_at: datetime


class SendResult(Protocol):
    status: str
    provider_message_id: str | None


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
    ) -> BookingResult: ...


class CrmToolPort(Protocol):
    def get_or_create_open_lead(self, *, tenant_id: str, phone: str, email: Any, name: str) -> tuple[Any, Any]: ...


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
    def get(self, session_id: str) -> Any: ...

    def record_event(self, session: Any, event_type: str, *, source: str, payload: dict[str, Any]) -> None: ...

    def enrich_context(self, session: Any, *, contact: Any, lead: Any, event_source: str) -> None: ...


@dataclass(frozen=True)
class ToolPorts:
    scheduling: SchedulingToolPort
    crm: CrmToolPort
    messaging: MessagingToolPort
    sessions: VoiceSessionToolPort
