"""CRM -- public API.

Boundary only: implementation still lives in legacy app.services.crm_*.
Services are imported lazily so importing this facade stays cheap and
patch targets on the legacy services keep working. Nothing returned here
is an ORM row: callers get immutable references they cannot mutate.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

__all__ = ["ContactRef", "ContactSnapshot", "CrmFacade", "LeadRef", "LeadSnapshot"]


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
