"""Pure rules for idempotent booking operations: types, states, key
normalisation and request fingerprints. No SQLAlchemy, provider or HTTP."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

OP_CREATE = "booking.create"
OP_CANCEL = "booking.cancel"
OP_RESCHEDULE = "booking.reschedule"

OP_PENDING = "pending"  # claimed locally, nothing sent to the provider yet
OP_PROVIDER_PENDING = "provider_pending"  # provider call is about to happen / in flight
OP_COMPLETED = "completed"
OP_FAILED = "failed"  # the provider definitively did not apply it: safe to retry
OP_PROVIDER_UNKNOWN = "provider_unknown"  # request sent, outcome unknown: NEVER retried blindly

IN_FLIGHT_STATES = frozenset({OP_PENDING, OP_PROVIDER_PENDING})

MAX_KEY_LENGTH = 128
_KEY_RE = re.compile(r"^[A-Za-z0-9._:\-]+$")


def normalize_idempotency_key(key: str | None) -> str | None:
    """None/blank -> None (no idempotency). Otherwise the key must be short,
    ASCII and free of whitespace; it is stored as given (never a secret)."""
    if key is None:
        return None
    key = key.strip()
    if not key:
        return None
    if len(key) > MAX_KEY_LENGTH or not _KEY_RE.match(key):
        raise ValueError("Invalid idempotency key: use up to 128 chars of A-Z a-z 0-9 . _ : -")
    return key


def _digest(parts: Mapping[str, Any]) -> str:
    canonical = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def create_fingerprint(
    *,
    tenant_id: str,
    lead_id: str,
    start_at: datetime,
    timezone: str | None,
    event_type_id: Any = None,
    event_type_slug: str | None = None,
    resource_id: str | None = None,
    team_id: str | None = None,
) -> str:
    """Identity of a create intent. Attendee data and notes are deliberately
    excluded: the same intent re-sent with a reworded note is still a retry."""
    return _digest(
        {
            "op": OP_CREATE,
            "tenant": tenant_id,
            "lead": lead_id,
            "start": _iso(start_at),
            "tz": timezone,
            "event_type_id": str(event_type_id) if event_type_id else None,
            "event_type_slug": event_type_slug,
            "resource": resource_id,
            "team": team_id,
        }
    )


def cancel_fingerprint(*, booking_id: str) -> str:
    return _digest({"op": OP_CANCEL, "booking": booking_id})


def reschedule_fingerprint(*, booking_id: str, new_start_at: datetime) -> str:
    return _digest({"op": OP_RESCHEDULE, "booking": booking_id, "new_start": _iso(new_start_at)})


def derived_cancel_key(booking_id: str) -> str:
    """A booking can be cancelled once: its id is the natural key."""
    return f"auto:{booking_id}"


def derived_reschedule_key(
    booking_id: str, current_start: datetime, last_rescheduled_at: datetime | None, new_start_at: datetime
) -> str:
    """No explicit key: dedupe concurrent identical requests only. The key
    changes with every completed reschedule (``last_rescheduled_at``), so
    moving A->B->A later is a new operation, not a replay."""
    return "auto:" + _digest(
        {
            "booking": booking_id,
            "from": _iso(current_start),
            "resched": _iso(last_rescheduled_at),
            "to": _iso(new_start_at),
        }
    )[:48]


_UNKNOWN_OUTCOME_MARKERS = ("timeout", "timedout", "connectionerror", "readerror", "remoteprotocolerror", "networkerror")


def is_outcome_unknown(exc: BaseException | None) -> bool:
    """True when the request may have reached the provider but its answer was
    lost (timeouts, dropped connections). Provider-neutral: matches on the
    exception chain's types, not on any SDK. Everything else is a definitive
    failure that is safe to retry."""
    seen = 0
    while exc is not None and seen < 8:
        if isinstance(exc, (TimeoutError, ConnectionError)):
            return True
        if any(m in type(exc).__name__.lower() for m in _UNKNOWN_OUTCOME_MARKERS):
            return True
        exc = exc.__cause__ or exc.__context__
        seen += 1
    return False
