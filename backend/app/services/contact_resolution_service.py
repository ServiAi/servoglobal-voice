from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crm import CrmContact, CrmLead
from app.schemas.session_context import (
    CallerContext,
    CampaignContext,
    ContactContext,
    LeadContext,
    SessionContextV1,
)
from app.services.voice_phone_service import VoicePhoneValidationError, normalize_caller_id


class ContactResolutionError(ValueError):
    pass


class CrossTenantResolutionError(ContactResolutionError):
    """An explicit contact_id/lead_id does not belong to the given tenant,
    or a lead_id/contact_id pair points at two different contacts. Always
    a hard failure -- never silently degraded to "unresolved", since that
    could mask a real cross-tenant bug or an attempted ID-guessing attack."""


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
    """

    def __init__(self, db: Session) -> None:
        self.db = db

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
        contact: CrmContact | None = None
        lead: CrmLead | None = None

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
    ) -> tuple[CrmContact | None, CrmLead | None]:
        lead: CrmLead | None = None
        contact: CrmContact | None = None
        if lead_id:
            lead = self.db.scalar(select(CrmLead).where(CrmLead.tenant_id == tenant_id, CrmLead.id == lead_id))
            if lead is None:
                raise CrossTenantResolutionError(f"lead_id '{lead_id}' does not belong to this tenant.")
            contact = lead.contact
        if contact_id:
            resolved_contact = self.db.scalar(
                select(CrmContact).where(CrmContact.tenant_id == tenant_id, CrmContact.id == contact_id)
            )
            if resolved_contact is None:
                raise CrossTenantResolutionError(f"contact_id '{contact_id}' does not belong to this tenant.")
            if contact is not None and contact.id != resolved_contact.id:
                raise CrossTenantResolutionError("lead_id does not belong to contact_id.")
            contact = resolved_contact
        return contact, lead

    def _lookup_contact_by_phone(self, tenant_id: str, phone: str) -> CrmContact | None:
        try:
            normalized = normalize_caller_id(phone)
        except VoicePhoneValidationError:
            # An unparseable/unsupported caller phone stays a known caller
            # (see resolve()) with no contact match -- never a hard error,
            # a malformed ANI must not break session creation.
            return None
        return self.db.scalar(
            select(CrmContact).where(CrmContact.tenant_id == tenant_id, CrmContact.phone_normalized == normalized)
        )

    @staticmethod
    def to_contact_context(contact: CrmContact) -> ContactContext:
        """Public because VoiceSessionService.enrich_context() reuses this
        exact mapping when enriching an already-created session's context
        (e.g. after crm.create_lead resolves a Contact/Lead) -- the safe
        representation logic must stay in one place, not be duplicated."""
        return ContactContext(id=contact.id, name=contact.name, phone=contact.phone, email=contact.email)

    @staticmethod
    def to_lead_context(lead: CrmLead) -> LeadContext:
        return LeadContext(id=lead.id, status=lead.status, stage=lead.stage.key if lead.stage else None)
