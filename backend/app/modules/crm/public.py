"""CRM -- public API.

Boundary only: implementation still lives in legacy app.services.crm_*.
Services are imported lazily so importing this facade stays cheap and
patch targets on the legacy services keep working. Nothing returned here
is an ORM row: callers get immutable references they cannot mutate.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

__all__ = [
    "CallState",
    "ContactRef",
    "ContactSnapshot",
    "CrmFacade",
    "LeadRef",
    "LeadSnapshot",
    "OutboundCallLedger",
    "OutboundContactRef",
]


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


def _contact_snapshot(row) -> ContactSnapshot:
    return ContactSnapshot(id=row.id, tenant_id=row.tenant_id, name=row.name, phone=row.phone, email=row.email)


def _lead_snapshot(row) -> LeadSnapshot:
    return LeadSnapshot(
        id=row.id,
        tenant_id=row.tenant_id,
        contact_id=row.contact_id,
        status=row.status,
        stage_key=row.stage.key if row.stage else None,
        campaign=row.campaign,
    )


class CrmFacade:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_or_create_open_lead(
        self, *, tenant_id: str, phone: str, email: str | None, name: str
    ) -> tuple[ContactRef, LeadRef]:
        """Idempotent: reuses the contact for ``phone`` and its open lead."""
        from app.services.crm_contact_service import CrmContactService
        from app.services.crm_lead_service import CrmLeadService

        contact = CrmContactService(self.db).get_or_create_contact(tenant_id, phone, email, name)
        lead = CrmLeadService(self.db).get_or_create_open_lead(tenant_id, contact.id)
        return (
            ContactRef(id=contact.id, tenant_id=contact.tenant_id),
            LeadRef(id=lead.id, tenant_id=lead.tenant_id, contact_id=lead.contact_id, status=lead.status),
        )

    # -- read-only snapshots (Voice builds SessionContextV1 from these) ------
    #
    # get_contact / get_lead are looked up by id only, NOT tenant-scoped:
    # callers must compare ``tenant_id`` themselves. That lets them fail
    # closed with a cross-tenant error instead of a silent "not found".

    def get_contact(self, contact_id: str) -> ContactSnapshot | None:
        from app.models.crm import CrmContact

        row = self.db.get(CrmContact, contact_id)
        return _contact_snapshot(row) if row is not None else None

    def get_lead(self, lead_id: str) -> LeadSnapshot | None:
        from app.models.crm import CrmLead

        row = self.db.get(CrmLead, lead_id)
        return _lead_snapshot(row) if row is not None else None

    def find_contact_by_normalized_phone(self, tenant_id: str, phone_normalized: str) -> ContactSnapshot | None:
        from sqlalchemy import select

        from app.models.crm import CrmContact

        row = self.db.scalar(
            select(CrmContact).where(CrmContact.tenant_id == tenant_id, CrmContact.phone_normalized == phone_normalized)
        )
        return _contact_snapshot(row) if row is not None else None

    def count_voice_calls_in_statuses(self, tenant_id: str, route_id: str, statuses: Sequence[str]) -> int:
        """CRM voice calls of the tenant holding a channel on the SIP route
        (Telephony's CallLoadPort, for the legacy provider-callback flow)."""
        from sqlalchemy import func, select

        from app.models.crm import CrmVoiceCall

        return int(
            self.db.scalar(
                select(func.count(CrmVoiceCall.id)).where(
                    CrmVoiceCall.tenant_id == tenant_id,
                    CrmVoiceCall.sip_route_id == route_id,
                    CrmVoiceCall.status.in_(tuple(statuses)),
                )
            )
            or 0
        )


@dataclass(frozen=True)
class OutboundContactRef:
    contact_id: str
    lead_id: str
    phone: str | None
    name: str | None


@dataclass(frozen=True)
class CallState:
    status: str
    provider_call_id: str | None


class OutboundCallLedger:
    """CRM's side of an outbound SIP call for one lead: resolves the lead's
    contact and keeps the CrmVoiceCall record in step with the call. Handed
    to Telephony (which sees only the ids and states below), so CrmLead /
    CrmContact / CrmVoiceCall rows never leave CRM. ``call_id`` is the
    CrmVoiceCall id once the call is opened (or found on an idempotent replay).
    """

    def __init__(self, db: Session, tenant_id: str, lead_id: str) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.lead_id = lead_id
        self.call_id: str | None = None

    def resolve_target(self) -> OutboundContactRef:
        from app.models.crm import CrmLead

        lead = self.db.get(CrmLead, self.lead_id)
        if lead is None or lead.tenant_id != self.tenant_id or lead.contact is None:
            raise ValueError("Lead does not exist or does not belong to this tenant.")
        if lead.contact.tenant_id != self.tenant_id:
            raise ValueError("Contact associated with this lead does not exist.")
        return OutboundContactRef(
            contact_id=lead.contact.id, lead_id=lead.id, phone=lead.contact.phone, name=lead.contact.name
        )

    def _call(self, call_id: str):
        from app.models.crm import CrmVoiceCall

        call = self.db.get(CrmVoiceCall, call_id)
        if call is None or call.tenant_id != self.tenant_id:
            raise ValueError("Idempotent voice call state is invalid.")
        return call

    def call_state(self, call_id: str) -> CallState:
        call = self._call(call_id)
        self.call_id = call.id
        return CallState(status=call.status, provider_call_id=call.provider_call_id)

    def open_call(self, *, sip_route_id: str, agent_version_id: str | None, to_phone: str, from_number: str) -> str:
        """Adds the CrmVoiceCall (flush, no commit)."""
        from app.models.crm import CrmLead, CrmVoiceCall

        lead = self.db.get(CrmLead, self.lead_id)
        call = CrmVoiceCall(
            tenant_id=self.tenant_id,
            lead_id=lead.id,
            contact_id=lead.contact.id,
            sip_route_id=sip_route_id,
            provider="livekit_sip",
            provider_agent_id=agent_version_id,
            direction="outbound",
            status="requested",
            to_phone=to_phone,
            from_number=from_number,
        )
        self.db.add(call)
        self.db.flush()
        self.call_id = call.id
        return call.id

    def mark_dialing(self, call_id: str) -> None:
        """Commits."""
        self.db.refresh(self._call(call_id))
        call = self._call(call_id)
        call.status = "dialing"
        call.started_at = datetime.now(UTC)
        self.db.commit()

    def mark_answered(self, call_id: str, provider_call_id: str | None) -> None:
        """No commit: the caller commits together with the projection."""
        call = self._call(call_id)
        call.provider_call_id = provider_call_id
        call.status = "answered"
        call.answered_at = datetime.now(UTC)

    def mark_failed(self, call_id: str, call_status: str, error_code: str) -> None:
        """No commit: committed with the session failure that follows."""
        call = self._call(call_id)
        self.db.refresh(call)
        call.status = call_status
        call.error_message = error_code[:255]
        call.ended_at = datetime.now(UTC)
