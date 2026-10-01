"""CRM -- public API.

Boundary only: implementation still lives in legacy app.services.crm_*.
Services are imported lazily so importing this facade stays cheap and
patch targets on the legacy services keep working. Nothing returned here
is an ORM row: callers get immutable references they cannot mutate.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

__all__ = ["ContactRef", "CrmFacade", "LeadRef"]


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
