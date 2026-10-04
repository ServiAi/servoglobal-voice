"""Voice Legacy adapter: Ultravox payload parsing for CRM call ingestion.

CRM application code never reads a provider payload: it asks this adapter (bound
in ``app.modules.crm.wiring``) for normalised values. Retire it together with the
Ultravox ingestion path.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.modules.crm.domain.calls import BookingDetection, CallClassification, CallRef, ContextLookup
from app.services.ultravox_booking_detector import CrmBookingDetectorService
from app.services.ultravox_call_classifier import CrmClassifierService
from app.services.ultravox_call_context_extractor import CrmContextExtractorService


def _call_obj(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = payload.get("call")
    return nested if isinstance(nested, dict) else {}


def _string_value(data: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if value is not None and value != "":
            return str(value)
    return None


class UltravoxCallPayloadAdapter:
    def __init__(self) -> None:
        self._extractor = CrmContextExtractorService()
        self._detector = CrmBookingDetectorService()
        self._classifier = CrmClassifierService()

    def event_type(self, payload: Mapping[str, Any]) -> str:
        event = payload.get("event") or payload.get("event_type") or payload.get("eventType")
        if isinstance(event, str):
            return event.strip().lower()
        return "call.updated"

    def context_lookup(self, payload: Mapping[str, Any]) -> ContextLookup:
        call = payload.get("call") if isinstance(payload.get("call"), dict) else payload
        metadata: dict[str, Any] = {}
        for candidate in (call.get("metadata"), payload.get("metadata"), payload.get("meta")):
            if isinstance(candidate, dict):
                metadata.update(candidate)
        initial_state = call.get("initialState") or call.get("initial_state")
        if isinstance(initial_state, dict):
            metadata.update({k: v for k, v in initial_state.items() if k not in metadata})
        return ContextLookup(
            external_call_id=_string_value(call, "callId", "call_id", "external_call_id"),
            form_submission_id=_string_value(metadata, "form_submission_id", "submission_id"),
            context_id=_string_value(metadata, "context_id", "crm_context_id"),
            phone=_string_value(
                metadata, "phone", "user_phone", "customer_phone", "lead_phone", "telefono", "celular", "mobile"
            )
            or _string_value(call, "customerPhone", "customer_phone", "phone"),
        )

    def extract_context(
        self, payload: Mapping[str, Any], call: CallRef | None, call_context: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        return self._extractor.extract(dict(payload), call_record=call, call_context=call_context)

    def summary_fields(self, payload: Mapping[str, Any], call: CallRef) -> tuple[str | None, str | None]:
        call_obj = _call_obj(payload)
        summary = call_obj.get("summary") or payload.get("summary") or call.summary
        short_summary = (
            call_obj.get("shortSummary")
            or call_obj.get("short_summary")
            or payload.get("shortSummary")
            or payload.get("short_summary")
            or call.short_summary
        )
        return summary, short_summary

    def end_reason(self, payload: Mapping[str, Any], call: CallRef) -> str:
        call_obj = _call_obj(payload)
        return call_obj.get("endReason") or call_obj.get("end_reason") or call.provider_status or "unknown"

    def billed_duration(self, payload: Mapping[str, Any]) -> Any:
        call_obj = _call_obj(payload)
        billed = (
            call_obj.get("billedDuration")
            or call_obj.get("billed_duration")
            or payload.get("billedDuration")
            or payload.get("billed_duration")
        )
        sip_details = (
            call_obj.get("sipDetails")
            or call_obj.get("sip_details")
            or payload.get("sipDetails")
            or payload.get("sip_details")
        )
        if not billed and isinstance(sip_details, dict):
            billed = sip_details.get("billedDuration") or sip_details.get("billed_duration")
        return billed

    def detect_booking(self, payload: Mapping[str, Any]) -> BookingDetection:
        result = self._detector.detect_successful_booking(dict(payload))
        return BookingDetection(created=result.created, event_id=result.event_id, start_time=result.start_time)

    def classify_after_call(
        self, call_status: str | None, summary: str | None, short_summary: str | None, payload: Mapping[str, Any]
    ) -> CallClassification:
        result = self._classifier.classify_after_call(call_status, summary, short_summary, dict(payload))
        return CallClassification(stage_key=result.stage_key, next_action=result.next_action)


def call_ref_from_call(call: Any) -> CallRef:
    """Analytics ``Call`` row -> the DTO CRM ingestion consumes (Voice Legacy
    side of the boundary: the row never enters CRM)."""
    return CallRef(
        id=call.id,
        tenant_id=call.tenant_id,
        external_provider=call.external_provider,
        external_call_id=call.external_call_id,
        customer_phone=call.customer_phone,
        normalized_status=call.normalized_status,
        provider_status=call.provider_status,
        joined_at=call.joined_at,
        summary=call.summary,
        short_summary=call.short_summary,
        duration_seconds=call.duration_seconds,
        billed_minutes=call.billed_minutes,
    )
