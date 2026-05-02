from __future__ import annotations

from app.models.analytics import NORMALIZED_CALL_STATUSES


class CallStatusNormalizer:
    _STATUS_MAP = {
        "active": "in_progress",
        "answered": "answered",
        "busy": "rejected",
        "cancel": "cancelled",
        "canceled": "cancelled",
        "cancelled": "cancelled",
        "completed": "answered",
        "connected": "answered",
        "declined": "rejected",
        "ended": "answered",
        "failed": "failed",
        "failure": "failed",
        "human_transfer": "transferred",
        "in_progress": "in_progress",
        "joined": "answered",
        "missed": "unanswered",
        "no_answer": "unanswered",
        "not_answered": "unanswered",
        "queued": "in_progress",
        "rejected": "rejected",
        "ringing": "in_progress",
        "started": "in_progress",
        "timeout": "unanswered",
        "transferred": "transferred",
        "voicemail": "voicemail",
    }

    def normalize(self, provider_status: str | None, fallback: str = "in_progress") -> str:
        normalized = self._STATUS_MAP.get((provider_status or "").strip().lower(), fallback)
        if normalized not in NORMALIZED_CALL_STATUSES:
            return "failed"
        return normalized
