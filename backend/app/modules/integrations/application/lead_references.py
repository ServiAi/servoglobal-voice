"""CRM deletes leads/contacts: the messaging history keeps its rows but drops the references."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from app.modules.integrations.infrastructure.models import CrmWhatsAppMessage, TenantEmailSend


def detach_lead_references(
    db: Session, *, tenant_id: str, lead_ids: Sequence[str], contact_ids: Sequence[str]
) -> None:
    for model in (CrmWhatsAppMessage, TenantEmailSend):
        db.execute(
            update(model)
            .where(
                model.tenant_id == tenant_id,
                or_(model.lead_id.in_(lead_ids), model.contact_id.in_(contact_ids)),
            )
            .values(lead_id=None, contact_id=None)
        )
