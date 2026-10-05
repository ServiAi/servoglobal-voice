"""Composition root of CRM: binds its ports to the rest of the platform.

The only place that knows who answers "is this user a member?", "which Analytics
call is this?", "detach bookings", and how provider payloads are parsed.
Application code depends on the Protocols in ``application/ports.py`` only.

Temporary legacy exceptions (allowlisted in ``test_crm_boundaries``):
``LegacyLeadHistory`` still touches Messaging (``CrmWhatsAppMessage``), Email
(``TenantEmailSend``) and Forms (``TenantFormToken``/``TenantFormSubmission``)
ORM, and ``UltravoxCallPayloadAdapter`` is a Voice Legacy adapter. Each is
replaced by that module's ``public.py`` when it is migrated (Messaging debt, not
CRM debt).
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, or_, update
from sqlalchemy.orm import Session

from app.modules.crm.application.ports import CrmPorts


class LegacyLeadHistory:
    """LeadHistoryPort over the not-yet-migrated Messaging / Email / Forms tables."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def clear_references(self, *, tenant_id: str, lead_ids: Sequence[str], contact_ids: Sequence[str]) -> None:
        from app.models.crm import CrmWhatsAppMessage
        from app.models.integrations import TenantEmailSend

        for model in (CrmWhatsAppMessage, TenantEmailSend):
            self.db.execute(
                update(model)
                .where(
                    model.tenant_id == tenant_id,
                    or_(model.lead_id.in_(lead_ids), model.contact_id.in_(contact_ids)),
                )
                .values(lead_id=None, contact_id=None)
            )

    def delete_form_artifacts(self, *, tenant_id: str, lead_ids: Sequence[str]) -> None:
        from app.models.integrations import TenantFormSubmission, TenantFormToken

        self.db.execute(
            delete(TenantFormSubmission).where(
                TenantFormSubmission.tenant_id == tenant_id,
                TenantFormSubmission.lead_id.in_(lead_ids),
            )
        )
        self.db.execute(
            delete(TenantFormToken).where(
                TenantFormToken.tenant_id == tenant_id,
                TenantFormToken.lead_id.in_(lead_ids),
            )
        )


class SchedulingDetach:
    """SchedulingPort -> scheduling.public."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def detach_customers(self, *, tenant_id: str, lead_ids: Sequence[str], contact_ids: Sequence[str]) -> None:
        from app.modules.scheduling.public import SchedulingFacade

        SchedulingFacade(self.db).detach_customers(tenant_id=tenant_id, lead_ids=lead_ids, contact_ids=contact_ids)


def default_crm_ports(db: Session) -> CrmPorts:
    from app.modules.analytics.public import CallLookup
    from app.modules.identity.public import MembershipDirectory
    from app.services.legacy_call_payload_adapter import UltravoxCallPayloadAdapter

    return CrmPorts(
        assignees=MembershipDirectory(db),
        scheduling=SchedulingDetach(db),
        history=LegacyLeadHistory(db),
        analytics=CallLookup(db),
        payloads=UltravoxCallPayloadAdapter(),
    )
