from __future__ import annotations

import re
from datetime import datetime
from typing import Any


def sanitize_google_calendar_error(value: str) -> str:
    cleaned = re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer [redacted]", value or "", flags=re.IGNORECASE)
    cleaned = re.sub(r"(access_token|refresh_token|client_secret)[^,\s}]*", r"\1=[redacted]", cleaned, flags=re.IGNORECASE)
    return cleaned[:300]


class GoogleCalendarService:
    def build_event_payload(
        self,
        *,
        summary: str,
        description: str | None,
        start_at: datetime,
        end_at: datetime,
        timezone: str,
        attendee_email: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "summary": summary,
            "description": description or "",
            "start": {"dateTime": start_at.isoformat(), "timeZone": timezone},
            "end": {"dateTime": end_at.isoformat(), "timeZone": timezone},
        }
        if attendee_email:
            payload["attendees"] = [{"email": attendee_email}]
        return payload

    def create_event(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ValueError("Google Calendar insert mode is not enabled yet.")
