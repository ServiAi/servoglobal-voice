"""Telephony capacity policy (pure)."""

from __future__ import annotations

# Statuses of the legacy provider-callback call records that hold a channel
# on a route. Those records are CRM data: Telephony only owns this list and
# asks for counts through CallLoadPort.
ACTIVE_CALLBACK_STATUSES = ("starting", "queued", "ringing", "in_progress")

VOICE_CAPACITY_REACHED = "voice_capacity_reached"
VOICE_CALLBACK_RECONCILED = "voice_callback_reconciled"
VOICE_CALLBACK_FORCED_RELEASE = "voice_callback_forced_release"
CAPACITY_EVENT_TYPES = (
    VOICE_CAPACITY_REACHED,
    VOICE_CALLBACK_RECONCILED,
    VOICE_CALLBACK_FORCED_RELEASE,
)

CAPACITY_END_REASON = "telephony_capacity_exceeded"


def is_at_capacity(active_calls: int, max_concurrent_calls: int) -> bool:
    return active_calls >= max_concurrent_calls
