"""Telephony's ledger for a public callback whose CRM call already exists.

The callback request created exactly one ``CrmVoiceCall``; Telephony must drive THAT record (never
open a second one). Everything goes through ``crm.public``; Telephony does not know the origin is a
Voice Experience.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.modules.crm.public import CrmVoiceCalls, UpdateVoiceCallCommand


@dataclass(frozen=True, slots=True)
class CallbackTarget:
    contact_id: str | None
    lead_id: str | None
    phone: str | None


@dataclass(frozen=True, slots=True)
class CallbackCallState:
    status: str
    provider_call_id: str | None


class VoiceExperienceCallbackLedger:
    def __init__(self, db: Session, tenant_id: str, call_id: str) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.call_id = call_id

    def _calls(self) -> CrmVoiceCalls:
        return CrmVoiceCalls(self.db)

    def _own(self, call_id: str):
        call = self._calls().get(call_id)
        if call is None or call.tenant_id != self.tenant_id or call_id != self.call_id:
            raise ValueError("Callback call record is invalid for this tenant.")
        return call

    def existing_call_id(self) -> str | None:
        return self.call_id

    def resolve_target(self) -> CallbackTarget:
        """Identity comes from the request's own call record (copied from the trusted submission)."""
        call = self._own(self.call_id)
        return CallbackTarget(contact_id=call.contact_id, lead_id=call.lead_id, phone=call.to_phone)

    def call_state(self, call_id: str) -> CallbackCallState:
        call = self._own(call_id)
        return CallbackCallState(status=call.status, provider_call_id=call.provider_call_id)

    def open_call(self, *, sip_route_id: str, agent_version_id: str | None, to_phone: str, from_number: str) -> str:
        """The record already exists: validate it and keep it (never a second call)."""
        self._own(self.call_id)
        return self.call_id

    def mark_dialing(self, call_id: str) -> None:
        """Commits."""
        self._own(call_id)
        self._calls().refresh(call_id)
        self._calls().update(call_id, UpdateVoiceCallCommand(status="dialing", started_at=datetime.now(UTC)))
        self.db.commit()

    def mark_answered(self, call_id: str, provider_call_id: str | None) -> None:
        """No commit: the caller commits together with the projection."""
        self._own(call_id)
        self._calls().update(
            call_id,
            UpdateVoiceCallCommand(provider_call_id=provider_call_id, status="answered", answered_at=datetime.now(UTC)),
        )

    def mark_failed(self, call_id: str, call_status: str, error_code: str) -> None:
        """No commit: committed with the session failure that follows."""
        self._own(call_id)
        self._calls().refresh(call_id)
        self._calls().update(
            call_id,
            UpdateVoiceCallCommand(status=call_status, error_message=error_code[:255], ended_at=datetime.now(UTC)),
        )
