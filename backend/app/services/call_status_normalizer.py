from __future__ import annotations

from app.models.analytics import NORMALIZED_CALL_STATUSES


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
