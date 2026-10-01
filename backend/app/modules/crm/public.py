"""CRM -- public API.

Boundary only: implementation still lives in legacy app.services.crm_*.
Services are imported lazily so importing this facade stays cheap and
patch targets on the legacy services keep working.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session


class CrmFacade:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_or_create_open_lead(self, *, tenant_id: str, phone: str, email: Any, name: str) -> tuple[Any, Any]:
        """Idempotent: reuses the contact for ``phone`` and its open lead.
        Returns ``(contact, lead)`` rows; callers read ids/status and may hand
        them to VoiceSessionFacade.enrich_context, nothing else."""
        from app.services.crm_contact_service import CrmContactService
        from app.services.crm_lead_service import CrmLeadService

        contact = CrmContactService(self.db).get_or_create_contact(tenant_id, phone, email, name)
        lead = CrmLeadService(self.db).get_or_create_open_lead(tenant_id, contact.id)
        return contact, lead
