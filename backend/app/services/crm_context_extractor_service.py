from __future__ import annotations

from typing import Any

from app.models.analytics import Call
from app.models.crm import CrmCallContext


NORMALIZED_CONTEXT_FIELDS = (
    "name",
    "email",
    "phone",
    "company",
    "interest",
    "industry",
    "use_case",
    "volume",
    "pain_point",
    "budget_range",
    "intent_level",
    "source",
    "campaign",
    "utm_source",
    "utm_campaign",
    "form_submission_id",
    "context_id",
)

FIELD_ALIASES = {
    "name": ("name", "user_name", "customer_name", "lead_name", "full_name", "nombre"),
    "email": ("email", "user_email", "customer_email", "lead_email", "correo"),
    "phone": ("phone", "user_phone", "customer_phone", "lead_phone", "telefono", "celular", "mobile"),
    "company": ("company", "company_name", "user_company", "empresa", "organization"),
    "interest": ("interest",),
    "industry": ("industry", "user_industry"),
    "use_case": ("use_case", "user_use_case", "useCase"),
    "volume": ("volume", "user_volume"),
    "pain_point": ("pain_point", "user_pain_point", "painPoint"),
    "budget_range": ("budget_range", "budgetRange"),
    "intent_level": ("intent_level", "intentLevel"),
    "source": ("source",),
    "campaign": ("campaign",),
    "utm_source": ("utm_source",),
    "utm_campaign": ("utm_campaign",),
    "form_submission_id": ("form_submission_id", "submission_id"),
    "context_id": ("context_id", "crm_context_id"),
}


class CrmContextExtractorService:
    def extract(
        self,
        payload: dict[str, Any],
        call_record: Call | None = None,
        call_context: CrmCallContext | None = None,
    ) -> dict[str, Any]:
        normalized = {field: None for field in NORMALIZED_CONTEXT_FIELDS}
        field_sources: dict[str, str] = {}

        for source_name, source_data in self._sources(payload, call_record, call_context):
            if source_data is None:
                continue
            for field in NORMALIZED_CONTEXT_FIELDS:
                if normalized[field] not in (None, ""):
                    continue
                value = self._field_value(source_data, field)
                if value not in (None, ""):
                    normalized[field] = str(value)
                    field_sources[field] = source_name

        normalized["field_sources"] = field_sources
        return normalized

    def _sources(
        self,
        payload: dict[str, Any],
        call_record: Call | None,
        call_context: CrmCallContext | None,
    ):
        call = payload.get("call") if isinstance(payload.get("call"), dict) else payload
        initial_state = call.get("initialState")
        initial_state_snake = call.get("initial_state")
        request_context = call.get("requestContext")
        request_context_snake = call.get("request_context")

        if call_context is not None:
            yield "crm_call_contexts", {
                field: getattr(call_context, field, None)
                for field in NORMALIZED_CONTEXT_FIELDS
            }
        yield "payload.call.metadata", call.get("metadata")
        yield "payload.metadata", payload.get("metadata")
        yield "payload.meta", payload.get("meta")
        yield "payload.call.initialState", initial_state
        yield "payload.call.initial_state", initial_state_snake
        yield "payload.call.initialState.context", self._dict_value(initial_state, "context")
        yield "payload.call.requestContext", request_context
        yield "payload.call.request_context", request_context_snake
        yield "payload.call.requestContext.context", self._dict_value(request_context, "context")
        yield "payload.call.customerPhone", {"phone": call.get("customerPhone") or call.get("customer_phone")}
        yield "payload.call.phone", {"phone": call.get("phone")}
        sip_details = call.get("sipDetails") or call.get("sip_details")
        yield "payload.call.sipDetails.from", {"phone": self._dict_value(sip_details, "from")}
        if call_record is not None:
            yield "call_record.customer_phone", {"phone": call_record.customer_phone}

    def _field_value(self, data: Any, field: str) -> Any:
        if not isinstance(data, dict):
            return None
        for key in FIELD_ALIASES[field]:
            value = data.get(key)
            if value not in (None, ""):
                return value
        return None

    def _dict_value(self, data: Any, key: str) -> Any:
        if isinstance(data, dict):
            return data.get(key)
        return None
