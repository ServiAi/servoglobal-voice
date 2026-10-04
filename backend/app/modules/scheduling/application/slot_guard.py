"""Local slot consistency for a resource.

Lock order used by every Scheduling flow (documented to avoid deadlocks):
operation (insert/update, no row lock held) -> resource row (FOR UPDATE, short,
no I/O) -> booking row. Overlap is half-open ``[start, end)`` over the
``SLOT_BLOCKING_STATUSES``. A PostgreSQL exclusion constraint
(``EXCLUDE USING gist`` + ``btree_gist``) could later reinforce this; the row
lock was chosen to avoid a new extension.

Only bookings that carry a ``scheduling_resource_id`` are protected. For
provider-assigned resources (Cal.com) the provider stays the source of truth.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.scheduling.domain.booking import SLOT_BLOCKING_STATUSES
from app.modules.scheduling.domain.errors import SlotConflictError
from app.modules.scheduling.infrastructure.models import CrmBooking, TenantSchedulingResource

logger = logging.getLogger(__name__)


def lock_resource(db: Session, tenant_id: str, resource_id: str) -> bool:
    row = db.execute(
        select(TenantSchedulingResource.id)
        .where(TenantSchedulingResource.id == resource_id, TenantSchedulingResource.tenant_id == tenant_id)
        .with_for_update()
    ).first()
    return row is not None


def has_overlap(
    db: Session,
    *,
    tenant_id: str,
    resource_id: str,
    start_at: datetime,
    end_at: datetime,
    exclude_booking_id: str | None,
) -> bool:
    stmt = select(CrmBooking.id).where(
        CrmBooking.tenant_id == tenant_id,
        CrmBooking.scheduling_resource_id == resource_id,
        CrmBooking.status.in_(SLOT_BLOCKING_STATUSES),
        CrmBooking.start_at < end_at,
        CrmBooking.end_at > start_at,
    )
    if exclude_booking_id:
        stmt = stmt.where(CrmBooking.id != exclude_booking_id)
    # A fresh statement: under READ COMMITTED it sees what the previous lock
    # holder committed.
    return db.execute(stmt.limit(1)).first() is not None


def claim_slot(
    db: Session,
    *,
    booking: CrmBooking,
    resource_id: str,
    start_at: datetime,
    end_at: datetime,
) -> None:
    """Lock the resource, re-check overlaps, stamp the booking with the resource
    and the interval (a reschedule is a tentative move) and commit (releasing the lock) BEFORE any provider call.

    Raises SlotConflictError (lock released) when another active booking holds
    the interval."""
    tenant_id = booking.tenant_id
    if not lock_resource(db, tenant_id, resource_id):
        db.rollback()
        raise SlotConflictError("Scheduling resource not found.")
    if has_overlap(
        db,
        tenant_id=tenant_id,
        resource_id=resource_id,
        start_at=start_at,
        end_at=end_at,
        exclude_booking_id=booking.id,
    ):
        db.rollback()
        logger.warning(
            "scheduling_slot_conflict tenant_id=%s resource_id=%s booking_id=%s", tenant_id, resource_id, booking.id
        )
        raise SlotConflictError()
    booking.scheduling_resource_id = resource_id
    booking.start_at = start_at
    booking.end_at = end_at
    db.commit()
