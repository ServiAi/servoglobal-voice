"""Bookings are operational history: when CRM deletes leads/contacts they stay,
only the references are cleared (same behaviour CRM had inline)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from app.modules.scheduling.infrastructure.models import CrmBooking


def detach_customers(db: Session, tenant_id: str, lead_ids: Sequence[str], contact_ids: Sequence[str]) -> None:
    db.execute(
        update(CrmBooking)
        .where(
            CrmBooking.tenant_id == tenant_id,
            or_(CrmBooking.lead_id.in_(lead_ids), CrmBooking.contact_id.in_(contact_ids)),
        )
        .values(lead_id=None, contact_id=None)
    )
