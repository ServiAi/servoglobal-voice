from __future__ import annotations

from dataclasses import dataclass
from typing import Any


BOOKING_TOOL_NAMES = {
    "crear_evento",
    "create_event",
    "create_calendar_event",
    "schedule_event",
    "book_appointment",
}

BOOKING_EVIDENCE_FIELDS = {
    "event_id",
    "calendar_event_id",
    "booking_id",
    "appointment_id",
    "htmlLink",
    "hangoutLink",
    "start",
    "start_time",
    "dateTime",
}

FAILED_STATUSES = {"error", "failed", "failure", "rejected"}


@dataclass(frozen=True)
class BookingDetectionResult:
    created: bool
    provider: str | None = None
    event_id: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    source: str | None = None
    confidence: str | None = None


class CrmBookingDetectorService:
    def detect_successful_booking(self, payload: dict[str, Any]) -> BookingDetectionResult:
        for item in self._walk_payload(payload):
            if not isinstance(item, dict):
                continue
            tool_name = self._tool_name(item)
            if tool_name not in BOOKING_TOOL_NAMES:
                continue
            if self._tool_failed(item):
                return BookingDetectionResult(created=False, source="tool_call", confidence="verified")
            evidence = self._booking_evidence(item)
            if evidence is None:
                return BookingDetectionResult(created=False, source="tool_call", confidence="verified")
            return BookingDetectionResult(
                created=True,
                provider=self._string(evidence.get("provider") or evidence.get("calendar_provider") or "google_calendar"),
                event_id=self._string(
                    evidence.get("event_id")
                    or evidence.get("calendar_event_id")
                    or evidence.get("booking_id")
                    or evidence.get("appointment_id")
                ),
                start_time=self._string(evidence.get("start_time") or evidence.get("start") or evidence.get("dateTime")),
                end_time=self._string(evidence.get("end_time") or evidence.get("end")),
                source="tool_call",
                confidence="verified",
            )
        return BookingDetectionResult(created=False)

    def _booking_evidence(self, item: dict[str, Any]) -> dict[str, Any] | None:
        candidates = [item]
        for key in ("result", "output", "response", "data"):
            value = item.get(key)
            if isinstance(value, dict):
                candidates.append(value)

        for candidate in candidates:
            if any(candidate.get(field) not in (None, "") for field in BOOKING_EVIDENCE_FIELDS):
                return candidate
        return None

    def _tool_name(self, item: dict[str, Any]) -> str | None:
        for key in ("toolName", "tool_name", "functionName", "function_name", "name"):
            value = item.get(key)
            if isinstance(value, str):
                return value.strip().lower()
        for key in ("tool", "function"):
            nested = item.get(key)
            if isinstance(nested, dict):
                value = nested.get("name")
                if isinstance(value, str):
                    return value.strip().lower()
        return None

    def _tool_failed(self, item: dict[str, Any]) -> bool:
        if "error" in item and item.get("error"):
            return True
        status_value = item.get("status") or item.get("outcome")
        result = item.get("result")
        if isinstance(result, dict):
            if "error" in result and result.get("error"):
                return True
            status_value = status_value or result.get("status") or result.get("outcome")
        return isinstance(status_value, str) and status_value.strip().lower() in FAILED_STATUSES

    def _walk_payload(self, value: Any):
        if isinstance(value, dict):
            yield value
            for nested in value.values():
                yield from self._walk_payload(nested)
        elif isinstance(value, list):
            for item in value:
                yield from self._walk_payload(item)

    def _string(self, value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(value)
