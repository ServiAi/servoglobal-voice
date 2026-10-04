"""Read/lookup operations behind ``crm.public``: ORM rows in, immutable views out.

Tenant-scoped unless the name says otherwise (``snapshot_*`` keep the historical
by-id semantics Voice relies on to detect cross-tenant mismatches).
"""

from __future__ import annotations

import re

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.modules.crm.domain.views import (
    ActivityView,
    CallContextView,
    ContactProfile,
    ContactSnapshot,
    LeadProfile,
    LeadSnapshot,
)
from app.modules.crm.infrastructure.models import (
    CrmActivity,
    CrmCallContext,
    CrmContact,
    CrmLead,
)


def _digits(phone: str | None) -> str | None:
    digits = re.sub(r"\D", "", phone or "")
    return digits or None


def contact_profile_of(row: CrmContact) -> ContactProfile:
    return ContactProfile(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        phone=row.phone,
        phone_normalized=row.phone_normalized,
        email=row.email,
        company=row.company,
        source=row.source,
    )


def lead_profile_of(row: CrmLead) -> LeadProfile:
    return LeadProfile(
        id=row.id,
        tenant_id=row.tenant_id,
        contact_id=row.contact_id,
        status=row.status,
        stage_key=row.stage.key if row.stage else None,
        stage_name=row.stage.name if row.stage else None,
        lead_score=row.lead_score,
        interest=row.interest,
        industry=row.industry,
        use_case=row.use_case,
        volume=row.volume,
        pain_point=row.pain_point,
        budget_range=row.budget_range,
        intent_level=row.intent_level,
        next_action=row.next_action,
        summary=row.summary,
        short_summary=row.short_summary,
        source=row.source,
        campaign=row.campaign,
        context_id=row.context_id,
        form_submission_id=row.form_submission_id,
        owner_agent_id=row.owner_agent_id,
        created_from_call_id=row.created_from_call_id,
        last_call_id=row.last_call_id,
        contact=contact_profile_of(row.contact) if row.contact else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def activity_view_of(row: CrmActivity) -> ActivityView:
    return ActivityView(
        id=row.id,
        tenant_id=row.tenant_id,
        lead_id=row.lead_id,
        contact_id=row.contact_id,
        call_id=row.call_id,
        activity_type=row.activity_type,
        title=row.title,
        description=row.description,
        outcome=row.outcome,
        occurred_at=row.occurred_at,
        payload=dict(row.payload_json or {}),
    )


def call_context_view_of(row: CrmCallContext) -> CallContextView:
    return CallContextView(
        id=row.id,
        tenant_id=row.tenant_id,
        external_provider=row.external_provider,
        external_call_id=row.external_call_id,
        form_submission_id=row.form_submission_id,
        context_id=row.context_id,
        phone=row.phone,
        phone_normalized=row.phone_normalized,
        email=row.email,
        name=row.name,
        company=row.company,
        interest=row.interest,
        industry=row.industry,
        use_case=row.use_case,
        volume=row.volume,
        pain_point=row.pain_point,
        budget_range=row.budget_range,
        intent_level=row.intent_level,
        source=row.source,
        campaign=row.campaign,
        utm_source=row.utm_source,
        utm_campaign=row.utm_campaign,
        status=row.status,
        created_at=row.created_at,
        raw_context=dict(row.raw_context_json or {}),
    )


class CrmDirectory:
    def __init__(self, db: Session) -> None:
        self.db = db

    # -- leads ---------------------------------------------------------------------
    def _lead_row(self, tenant_id: str, lead_id: str) -> CrmLead | None:
        return self.db.scalar(
            select(CrmLead)
            .options(joinedload(CrmLead.contact), joinedload(CrmLead.stage))
            .where(CrmLead.tenant_id == tenant_id, CrmLead.id == lead_id)
        )

    def lead_profile(self, tenant_id: str, lead_id: str) -> LeadProfile | None:
        row = self._lead_row(tenant_id, lead_id)
        return lead_profile_of(row) if row is not None else None

    def lead_profile_for_context(self, tenant_id: str, context_id: str) -> LeadProfile | None:
        row = self.db.scalar(
            select(CrmLead)
            .options(joinedload(CrmLead.contact), joinedload(CrmLead.stage))
            .where(CrmLead.tenant_id == tenant_id, CrmLead.context_id == context_id)
        )
        return lead_profile_of(row) if row is not None else None

    def open_lead_for_contact(self, tenant_id: str, contact_id: str) -> LeadProfile | None:
        row = self.db.scalar(
            select(CrmLead)
            .options(joinedload(CrmLead.contact), joinedload(CrmLead.stage))
            .where(CrmLead.tenant_id == tenant_id, CrmLead.contact_id == contact_id, CrmLead.status == "open")
            .order_by(CrmLead.created_at.desc())
        )
        return lead_profile_of(row) if row is not None else None

    def snapshot_lead(self, lead_id: str) -> LeadSnapshot | None:
        """By id only, NOT tenant-scoped: callers compare ``tenant_id`` themselves
        (Voice fails closed on a cross-tenant id instead of a silent "not found")."""
        row = self.db.get(CrmLead, lead_id)
        if row is None:
            return None
        return LeadSnapshot(
            id=row.id,
            tenant_id=row.tenant_id,
            contact_id=row.contact_id,
            status=row.status,
            stage_key=row.stage.key if row.stage else None,
            campaign=row.campaign,
        )

    # -- contacts ------------------------------------------------------------------
    def contact_profile(self, tenant_id: str, contact_id: str) -> ContactProfile | None:
        row = self.db.scalar(select(CrmContact).where(CrmContact.tenant_id == tenant_id, CrmContact.id == contact_id))
        return contact_profile_of(row) if row is not None else None

    def snapshot_contact(self, contact_id: str) -> ContactSnapshot | None:
        row = self.db.get(CrmContact, contact_id)
        return self._contact_snapshot(row)

    def find_contact_by_normalized_phone(self, tenant_id: str, phone_normalized: str) -> ContactSnapshot | None:
        row = self.db.scalar(
            select(CrmContact).where(CrmContact.tenant_id == tenant_id, CrmContact.phone_normalized == phone_normalized)
        )
        return self._contact_snapshot(row)

    def find_contact_by_phone_digits(self, tenant_id: str, phone: str | None) -> ContactProfile | None:
        """The tenant's contact whose stored phone has the same digits as ``phone``
        (country prefixes and punctuation are not interpreted: WhatsApp sends E.164
        without ``+``)."""
        digits = _digits(phone)
        if not digits:
            return None
        for contact in self.db.scalars(select(CrmContact).where(CrmContact.tenant_id == tenant_id)).all():
            if _digits(contact.phone_normalized) == digits or _digits(contact.phone) == digits:
                return contact_profile_of(contact)
        return None

    @staticmethod
    def _contact_snapshot(row: CrmContact | None) -> ContactSnapshot | None:
        if row is None:
            return None
        return ContactSnapshot(id=row.id, tenant_id=row.tenant_id, name=row.name, phone=row.phone, email=row.email)

    # -- timeline -------------------------------------------------------------------
    def has_activity(self, tenant_id: str, lead_id: str, deduplication_key: str) -> bool:
        return (
            self.db.scalar(
                select(CrmActivity.id).where(
                    CrmActivity.tenant_id == tenant_id,
                    CrmActivity.lead_id == lead_id,
                    CrmActivity.deduplication_key == deduplication_key,
                )
            )
            is not None
        )

    def lead_activities(self, tenant_id: str, lead_id: str) -> list[ActivityView]:
        rows = self.db.scalars(
            select(CrmActivity)
            .where(CrmActivity.tenant_id == tenant_id, CrmActivity.lead_id == lead_id)
            .order_by(CrmActivity.occurred_at.desc())
        ).all()
        return [activity_view_of(row) for row in rows]

    # -- call contexts ----------------------------------------------------------------
    def call_context_by_any_id(self, call_context_id: str) -> CallContextView | None:
        """By CRM id or public ``context_id`` (the voice tool path has no tenant yet)."""
        row = self.db.scalar(
            select(CrmCallContext).where(
                or_(CrmCallContext.id == call_context_id, CrmCallContext.context_id == call_context_id)
            )
        )
        return call_context_view_of(row) if row is not None else None

    def call_context_for_lead(self, tenant_id: str, context_id: str) -> CallContextView | None:
        row = self.db.scalar(
            select(CrmCallContext)
            .where(
                CrmCallContext.tenant_id == tenant_id,
                or_(CrmCallContext.id == context_id, CrmCallContext.context_id == context_id),
            )
            .order_by(CrmCallContext.created_at.desc())
        )
        return call_context_view_of(row) if row is not None else None
