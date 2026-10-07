"""Call status vocabulary and provider-status normalization (framework-free)."""

from __future__ import annotations

NORMALIZED_CALL_STATUSES = (
    "in_progress",
    "answered",
    "unanswered",
    "rejected",
    "failed",
    "cancelled",
    "transferred",
    "voicemail",
)
ACTIVE_STATUS = "in_progress"
ANSWERED_STATUS = "answered"
UNANSWERED_STATUS = "unanswered"
TERMINAL_CALL_STATUSES = frozenset(NORMALIZED_CALL_STATUSES) - {ACTIVE_STATUS}


class CallStatusNormalizer:
    _STATUS_MAP = {
        "active": "in_progress",
        "answered": "answered",
        "agent_hangup": "answered",
        "busy": "rejected",
        "billing_status_free_system_error": "failed",
        "cancel": "cancelled",
        "canceled": "cancelled",
        "cancelled": "cancelled",
        "call.billed": "answered",
        "call.ended": "answered",
        "call.joined": "in_progress",
        "call.started": "in_progress",
        "completed": "answered",
        "connected": "answered",
        "connection_error": "failed",
        "declined": "rejected",
        "ended": "answered",
        "failed": "failed",
        "failure": "failed",
        "hangup": "answered",
        "human_transfer": "transferred",
        "in_progress": "in_progress",
        "joined": "in_progress",
        "missed": "unanswered",
        "no_answer": "unanswered",
        "not_answered": "unanswered",
        "queued": "in_progress",
        "rejected": "rejected",
        "ringing": "in_progress",
        "started": "in_progress",
        "system_error": "failed",
        "timeout": "unanswered",
        "transferred": "transferred",
        "unjoined": "unanswered",
        "voicemail": "voicemail",
    }

    def normalize(self, provider_status: str | None, fallback: str = "in_progress") -> str:
        normalized = self._STATUS_MAP.get((provider_status or "").strip().lower(), fallback)
        if normalized not in NORMALIZED_CALL_STATUSES:
            return "failed"
        return normalized


def is_status_regression(current_status: str | None, incoming_status: str | None, *, partial_update: bool) -> bool:
    """A late partial update must never reopen a call that already finished."""
    return bool(
        partial_update and current_status in TERMINAL_CALL_STATUSES and incoming_status == ACTIVE_STATUS
    )
