"""Idempotent booking operations.

``begin`` claims ``(tenant, type, key)`` with an INSERT: the unique constraint,
not a prior SELECT, decides concurrent retries. The loser reloads the winner's
row and either replays its result, waits briefly for it, or reports a
recoverable in-progress state. No DB lock is held while waiting or while the
provider is called.

Guarantee: at most one *local* logical operation per key, safe retries where the
provider outcome is known, and ``provider_unknown`` (never auto-retried) where
it is not. This is NOT exactly-once against Google/Cal.com.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.scheduling.domain.errors import (
    BookingOperationInProgressError,
    IdempotencyConflictError,
)
from app.modules.scheduling.domain.operations import (
    IN_FLIGHT_STATES,
    OP_COMPLETED,
    OP_FAILED,
    OP_PENDING,
    OP_PROVIDER_PENDING,
    OP_PROVIDER_UNKNOWN,
)
from app.modules.scheduling.infrastructure.models import BookingOperation

logger = logging.getLogger(__name__)

WAIT_SECONDS = 10.0
POLL_INTERVAL = 0.05


@dataclass(frozen=True)
class Begun:
    """``owner`` -> this caller runs the operation; otherwise ``operation`` is a
    completed one to replay."""

    operation: BookingOperation
    owner: bool


def _log(event: str, op: BookingOperation) -> None:
    # Ids and states only: never tokens, provider keys or attendee data.
    logger.info(
        "scheduling_%s tenant_id=%s operation_id=%s booking_id=%s operation_type=%s provider=%s status=%s",
        event, op.tenant_id, op.id, op.booking_id, op.operation_type, op.provider, op.status,
    )


class BookingOperationService:
    def __init__(self, db: Session, *, wait_seconds: float = WAIT_SECONDS) -> None:
        self.db = db
        self.wait_seconds = wait_seconds

    def _load(self, tenant_id: str, operation_type: str, key: str) -> BookingOperation | None:
        return self.db.scalar(
            select(BookingOperation)
            .where(
                BookingOperation.tenant_id == tenant_id,
                BookingOperation.operation_type == operation_type,
                BookingOperation.idempotency_key == key,
            )
            .execution_options(populate_existing=True)
        )

    def begin(
        self,
        *,
        tenant_id: str,
        operation_type: str,
        key: str,
        fingerprint: str,
        booking_id: str | None = None,
    ) -> Begun:
        op = BookingOperation(
            tenant_id=tenant_id,
            operation_type=operation_type,
            idempotency_key=key,
            request_fingerprint=fingerprint,
            booking_id=booking_id,
            status=OP_PENDING,
        )
        self.db.add(op)
        try:
            self.db.commit()
            return Begun(op, owner=True)
        except IntegrityError:
            self.db.rollback()

        existing = self._load(tenant_id, operation_type, key)
        if existing is None:  # deleted between insert and reload: claim again
            return self.begin(
                tenant_id=tenant_id, operation_type=operation_type, key=key,
                fingerprint=fingerprint, booking_id=booking_id,
            )
        if existing.request_fingerprint != fingerprint:
            logger.warning("scheduling_idempotency_conflict tenant_id=%s operation_type=%s", tenant_id, operation_type)
            raise IdempotencyConflictError()

        existing = self._settle(existing)
        if existing.status == OP_COMPLETED:
            logger.info("scheduling_idempotency_replay tenant_id=%s operation_type=%s", tenant_id, operation_type)
            return Begun(existing, owner=False)
        if existing.status == OP_FAILED and self._reclaim(existing):
            return Begun(self._load(tenant_id, operation_type, key) or existing, owner=True)
        _log("operation_in_progress", existing)
        raise BookingOperationInProgressError(
            "Provider outcome is uncertain for this operation; it will not be repeated automatically."
            if existing.status == OP_PROVIDER_UNKNOWN
            else "A booking operation with this key is still in progress."
        )

    def _settle(self, op: BookingOperation) -> BookingOperation:
        """Wait (bounded, lock-free) while another caller owns the operation."""
        deadline = time.monotonic() + self.wait_seconds
        while op.status in IN_FLIGHT_STATES and time.monotonic() < deadline:
            self.db.rollback()  # end the read transaction: nothing held while sleeping
            time.sleep(POLL_INTERVAL)
            fresh = self._load(op.tenant_id, op.operation_type, op.idempotency_key)
            if fresh is None:
                break
            op = fresh
        self.db.rollback()
        return op

    def _reclaim(self, op: BookingOperation) -> bool:
        """failed -> pending, atomically: exactly one retrying caller wins."""
        result = self.db.execute(
            update(BookingOperation)
            .where(BookingOperation.id == op.id, BookingOperation.status == OP_FAILED)
            .values(status=OP_PENDING, error_code=None, completed_at=None)
        )
        self.db.commit()
        return result.rowcount == 1

    def mark_provider_pending(self, op: BookingOperation, *, provider: str, booking_id: str | None = None) -> None:
        op.status = OP_PROVIDER_PENDING
        op.provider = provider
        if booking_id:
            op.booking_id = booking_id
        self.db.commit()

    def complete(self, op: BookingOperation, *, booking_id: str | None = None, result: dict | None = None) -> None:
        op.status = OP_COMPLETED
        op.completed_at = datetime.now(UTC)
        if booking_id:
            op.booking_id = booking_id
        op.result_json = result
        self.db.commit()
        _log("operation_completed", op)

    def fail(self, op: BookingOperation, *, error_code: str) -> None:
        op.status = OP_FAILED
        op.error_code = error_code[:80]
        op.completed_at = datetime.now(UTC)
        self.db.commit()
        _log("operation_failed", op)

    def mark_unknown(self, op: BookingOperation, *, error_code: str) -> None:
        op.status = OP_PROVIDER_UNKNOWN
        op.error_code = error_code[:80]
        self.db.commit()
        logger.warning(
            "scheduling_provider_unknown tenant_id=%s operation_id=%s operation_type=%s",
            op.tenant_id, op.id, op.operation_type,
        )
