"""VoiceSession state machine (pure)."""

from __future__ import annotations

from datetime import UTC, datetime

TRANSITIONS: dict[str, set[str]] = {
    "requested": {"dispatching", "failed", "cancelled"},
    "dispatching": {"dispatched", "failed", "cancelled"},
    "dispatched": {"starting", "ended", "failed", "cancelled"},
    "starting": {"connected", "ended", "failed", "cancelled"},
    "connected": {"ending", "ended", "failed", "cancelled"},
    "ending": {"ended", "failed", "cancelled"},
    "ended": set(),
    "failed": set(),
    "cancelled": set(),
}

TERMINAL_STATUSES = frozenset({"ended", "failed", "cancelled"})

# Runtime event -> session status it moves the session to (when allowed).
RUNTIME_EVENT_TARGETS = {
    "voice.session.started": "starting",
    "voice.session.connected": "connected",
    "voice.session.ended": "ended",
    "voice.session.failed": "failed",
}


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, set())


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
