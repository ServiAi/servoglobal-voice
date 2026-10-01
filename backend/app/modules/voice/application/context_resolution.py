from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.telephony.public import VoicePhoneValidationError, normalize_caller_id
from app.modules.voice.application.ports import ContactView, CrmContextPort, LeadView
from app.modules.voice.domain.errors import (
    ContactResolutionError,
    CrossTenantResolutionError,
)
from app.modules.voice.domain.session_context import (
    CallerContext,
    CampaignContext,
    ContactContext,
    LeadContext,
    SessionContextV1,
)

__all__ = ["ContactResolutionError", "ContactResolutionService", "CrossTenantResolutionError"]


class ContactResolutionService:
    """Resolves the tenant-scoped business context of a VoiceSession: who's
    calling and, if possible, which Contact/Lead they represent. Never
    creates a Contact or Lead -- an unknown caller stays
    caller-known/contact-unresolved/lead-unresolved; creating a lead from
    an unresolved caller is always a separate, explicit action elsewhere
    (e.g. the crm.create_lead tool), never a side effect of resolution.

    Precedence: explicit `contact_id`/`lead_id` only when `trusted_ids=True`
    (the caller must be an authenticated internal component asserting an
    ID it already knows to be correct -- never a bare pass-through of
    caller/LLM-supplied input) -> lookup by normalized phone -> unresolved.

    Voice owns how SessionContextV1 is built; CRM owns how contacts/leads
    are read, and only hands over snapshots (CrmContextPort).
    """

    def __init__(self, db: Session, crm: CrmContextPort | None = None) -> None:
        self.db = db
        if crm is None:
            from app.modules.voice.wiring import crm_context

            crm = crm_context(db)
        self.crm = crm

    def resolve(
        self,
        *,
        tenant_id: str,
        phone: str | None = None,
        contact_id: str | None = None,
        lead_id: str | None = None,
        trusted_ids: bool = False,
        source: str | None = None,
        variables: dict | None = None,
    ) -> SessionContextV1:
        contact: ContactView | None = None
        lead: LeadView | None = None

        if trusted_ids and (contact_id or lead_id):
            contact, lead = self._resolve_trusted_ids(tenant_id, contact_id=contact_id, lead_id=lead_id)
        elif phone:
            contact = self._lookup_contact_by_phone(tenant_id, phone)

        return SessionContextV1(
            source=source,
            caller=CallerContext(phone=phone) if phone else None,
            contact=self.to_contact_context(contact) if contact else None,
            lead=self.to_lead_context(lead) if lead else None,
            campaign=CampaignContext(name=lead.campaign) if lead and lead.campaign else None,
            variables=variables or {},
        )

    def _resolve_trusted_ids(
        self, tenant_id: str, *, contact_id: str | None, lead_id: str | None
    ) -> tuple[ContactView | None, LeadView | None]:
        lead: LeadView | None = None
        contact: ContactView | None = None
        if lead_id:
            lead = self.crm.get_lead(lead_id)
            if lead is None or lead.tenant_id != tenant_id:
                raise CrossTenantResolutionError(f"lead_id '{lead_id}' does not belong to this tenant.")
            contact = self.crm.get_contact(lead.contact_id)
        if contact_id:
            resolved_contact = self.crm.get_contact(contact_id)
            if resolved_contact is None or resolved_contact.tenant_id != tenant_id:
                raise CrossTenantResolutionError(f"contact_id '{contact_id}' does not belong to this tenant.")
            if contact is not None and contact.id != resolved_contact.id:
                raise CrossTenantResolutionError("lead_id does not belong to contact_id.")
            contact = resolved_contact
        return contact, lead

    def _lookup_contact_by_phone(self, tenant_id: str, phone: str) -> ContactView | None:
        try:
            normalized = normalize_caller_id(phone)
        except VoicePhoneValidationError:
            # An unparseable/unsupported caller phone stays a known caller
            # (see resolve()) with no contact match -- never a hard error,
            # a malformed ANI must not break session creation.
            return None
        return self.crm.find_contact_by_normalized_phone(tenant_id, normalized)

    @staticmethod
    def to_contact_context(contact: ContactView) -> ContactContext:
        """Public because VoiceSessionService.enrich_context() reuses this
        exact mapping when enriching an already-created session's context
        (e.g. after crm.create_lead resolves a Contact/Lead) -- the safe
        representation logic must stay in one place, not be duplicated."""
        return ContactContext(id=contact.id, name=contact.name, phone=contact.phone, email=contact.email)

    @staticmethod
    def to_lead_context(lead: LeadView) -> LeadContext:
        return LeadContext(id=lead.id, status=lead.status, stage=lead.stage_key)
