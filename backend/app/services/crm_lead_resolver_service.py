from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analytics import Call
from app.models.crm import CrmCallContext, CrmContact, CrmLead
from app.services.crm_contact_service import normalize_phone
from app.services.crm_pipeline_service import CrmPipelineService


logger = logging.getLogger(__name__)


class CrmLeadResolverService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.pipeline_service = CrmPipelineService(db)

    def resolve_existing_lead_for_call(
        self,
        tenant_id: str,
        call: Call,
        contact_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> CrmLead | None:
        external_call_id = self._value(context, "external_call_id", "call_id", "callId") or call.external_call_id
        context_id = self._value(context, "context_id", "crm_context_id")
        form_submission_id = self._value(context, "form_submission_id", "submission_id")

        lead = self._lead_by_context_id(tenant_id, context_id)
        if lead:
            return lead

        lead = self._lead_by_form_submission_id(tenant_id, form_submission_id)
        if lead:
            return lead

        if external_call_id:
            related_call = self.db.scalar(
                select(Call)
                .where(
                    Call.tenant_id == tenant_id,
                    Call.external_provider == call.external_provider,
                    Call.external_call_id == external_call_id,
                )
                .limit(1)
            )
            if related_call:
                lead = self._lead_by_call_id(tenant_id, related_call.id, created_first=True)
                if lead:
                    return lead

        if call.id:
            lead = self._lead_by_call_id(tenant_id, call.id, created_first=True)
            if lead:
                return lead

        call_context = self._find_call_context(tenant_id, call, context, external_call_id)
        if call_context:
            lead = self._lead_from_context(tenant_id, call_context)
            if lead:
                return lead

        phone = self._value(context, "phone", "user_phone", "customer_phone", "lead_phone") or call.customer_phone
        lead = self._lead_by_phone(tenant_id, phone)
        if lead:
            return lead

        email = self._value(context, "email", "user_email", "customer_email", "lead_email")
        lead = self._lead_by_email(tenant_id, email)
        if lead:
            return lead

        if contact_id:
            return self._open_lead_for_contact(tenant_id, contact_id)

        return None

    def resolve_or_create_lead_for_new_context(
        self,
        tenant_id: str,
        contact: CrmContact,
        metadata: dict | None = None,
        *,
        call: Call | None = None,
    ) -> CrmLead:
        meta = metadata or {}
        lead = self.resolve_existing_lead_for_call(tenant_id, call, contact.id, meta) if call else None
        if lead is None:
            lead = self._lead_by_context_id(tenant_id, self._value(meta, "context_id", "crm_context_id"))
        if lead is None:
            lead = self._lead_by_form_submission_id(tenant_id, self._value(meta, "form_submission_id", "submission_id"))
        if lead is None:
            lead = self._open_new_stage_lead_for_contact(tenant_id, contact.id)

        if lead is None:
            stage = self.pipeline_service.get_stage_by_key(tenant_id, "new")
            lead = CrmLead(
                tenant_id=tenant_id,
                contact_id=contact.id,
                current_stage_id=stage.id,
                status="open",
                created_from_call_id=call.id if call and call.id else None,
                last_call_id=call.id if call and call.id else None,
                form_submission_id=meta.get("form_submission_id"),
                context_id=meta.get("context_id"),
                interest=meta.get("interest"),
                industry=meta.get("industry"),
                use_case=meta.get("use_case"),
                volume=meta.get("volume"),
                pain_point=meta.get("pain_point"),
                budget_range=meta.get("budget_range"),
                intent_level=meta.get("intent_level"),
                source=meta.get("source"),
                campaign=meta.get("campaign"),
            )
            self.db.add(lead)
            self.db.commit()
            self.db.refresh(lead)
            return lead

        self._attach_call(lead, call)
        self._enrich_lead_fields(lead, meta)
        self.db.commit()
        self.db.refresh(lead)
        return lead

    def resolve_or_create_lead_for_connected_call(
        self,
        tenant_id: str,
        call: Call,
        contact: CrmContact,
        metadata: dict | None = None,
        *,
        stage_key: str = "connected",
    ) -> CrmLead:
        meta = metadata or {}
        lead = self.resolve_existing_lead_for_call(tenant_id, call, contact.id, meta)

        if lead is None:
            stage = self.pipeline_service.get_stage_by_key(tenant_id, stage_key)
            lead = CrmLead(
                tenant_id=tenant_id,
                contact_id=contact.id,
                current_stage_id=stage.id,
                status="open",
                created_from_call_id=call.id,
                last_call_id=call.id,
                form_submission_id=meta.get("form_submission_id"),
                context_id=meta.get("context_id"),
                interest=meta.get("interest"),
                industry=meta.get("industry"),
                use_case=meta.get("use_case"),
                volume=meta.get("volume"),
                pain_point=meta.get("pain_point"),
                budget_range=meta.get("budget_range"),
                intent_level=meta.get("intent_level"),
                source=meta.get("source"),
                campaign=meta.get("campaign"),
            )
            self.db.add(lead)
            self.db.commit()
            self.db.refresh(lead)
            return lead

        self._attach_call(lead, call)
        self._enrich_lead_fields(lead, meta)
        self.db.commit()
        self.db.refresh(lead)
        return lead

    def _lead_by_call_id(self, tenant_id: str, call_id: str, *, created_first: bool) -> CrmLead | None:
        fields = (CrmLead.created_from_call_id, CrmLead.last_call_id)
        if not created_first:
            fields = tuple(reversed(fields))

        for field in fields:
            lead = self.db.scalar(
                select(CrmLead)
                .where(
                    CrmLead.tenant_id == tenant_id,
                    field == call_id,
                )
                .order_by(CrmLead.updated_at.desc())
                .limit(1)
            )
            if lead:
                return lead
        return None

    def _lead_by_context_id(self, tenant_id: str, context_id: str | None) -> CrmLead | None:
        if not context_id:
            return None
        return self.db.scalar(
            select(CrmLead)
            .where(
                CrmLead.tenant_id == tenant_id,
                CrmLead.context_id == context_id,
            )
            .order_by(CrmLead.updated_at.desc())
            .limit(1)
        )

    def _lead_by_form_submission_id(self, tenant_id: str, form_submission_id: str | None) -> CrmLead | None:
        if not form_submission_id:
            return None
        return self.db.scalar(
            select(CrmLead)
            .where(
                CrmLead.tenant_id == tenant_id,
                CrmLead.form_submission_id == form_submission_id,
            )
            .order_by(CrmLead.updated_at.desc())
            .limit(1)
        )

    def _find_call_context(
        self,
        tenant_id: str,
        call: Call,
        context: dict[str, Any] | None,
        external_call_id: str | None,
    ) -> CrmCallContext | None:
        filters = []
        if external_call_id:
            filters.append(
                (
                    CrmCallContext.external_provider == call.external_provider,
                    CrmCallContext.external_call_id == external_call_id,
                )
            )

        form_submission_id = self._value(context, "form_submission_id", "submission_id")
        if form_submission_id:
            filters.append((CrmCallContext.form_submission_id == form_submission_id,))

        context_id = self._value(context, "context_id", "crm_context_id")
        if context_id:
            filters.append((CrmCallContext.context_id == context_id,))

        for conditions in filters:
            found = self.db.scalar(
                select(CrmCallContext)
                .where(CrmCallContext.tenant_id == tenant_id, *conditions)
                .order_by(CrmCallContext.created_at.desc())
                .limit(1)
            )
            if found:
                return found
        return None

    def _lead_from_context(self, tenant_id: str, call_context: CrmCallContext) -> CrmLead | None:
        lead = self._lead_by_context_id(tenant_id, call_context.context_id)
        if lead:
            return lead

        lead = self._lead_by_form_submission_id(tenant_id, call_context.form_submission_id)
        if lead:
            return lead

        if call_context.external_call_id:
            related_call = self.db.scalar(
                select(Call)
                .where(
                    Call.tenant_id == tenant_id,
                    Call.external_provider == call_context.external_provider,
                    Call.external_call_id == call_context.external_call_id,
                )
                .limit(1)
            )
            if related_call:
                lead = self._lead_by_call_id(tenant_id, related_call.id, created_first=True)
                if lead:
                    return lead

        lead = self._lead_by_phone(tenant_id, call_context.phone)
        if lead:
            return lead
        return self._lead_by_email(tenant_id, call_context.email)

    def _lead_by_phone(self, tenant_id: str, phone: str | None) -> CrmLead | None:
        phone_normalized = normalize_phone(phone)
        if not phone_normalized:
            return None
        contact = self.db.scalar(
            select(CrmContact)
            .where(
                CrmContact.tenant_id == tenant_id,
                CrmContact.phone_normalized == phone_normalized,
            )
            .limit(1)
        )
        return self._open_lead_for_contact(tenant_id, contact.id) if contact else None

    def _lead_by_email(self, tenant_id: str, email: str | None) -> CrmLead | None:
        if not email:
            return None
        contact = self.db.scalar(
            select(CrmContact)
            .where(
                CrmContact.tenant_id == tenant_id,
                CrmContact.email == email,
            )
            .limit(1)
        )
        return self._open_lead_for_contact(tenant_id, contact.id) if contact else None

    def _open_lead_for_contact(self, tenant_id: str, contact_id: str) -> CrmLead | None:
        return self.db.scalar(
            select(CrmLead)
            .where(
                CrmLead.tenant_id == tenant_id,
                CrmLead.contact_id == contact_id,
                CrmLead.status == "open",
            )
            .order_by(CrmLead.updated_at.desc())
            .limit(1)
        )

    def _open_new_stage_lead_for_contact(self, tenant_id: str, contact_id: str) -> CrmLead | None:
        stage = self.pipeline_service.get_stage_by_key(tenant_id, "new")
        if stage is None:
            return None
        return self.db.scalar(
            select(CrmLead)
            .where(
                CrmLead.tenant_id == tenant_id,
                CrmLead.contact_id == contact_id,
                CrmLead.status == "open",
                CrmLead.current_stage_id == stage.id,
            )
            .order_by(CrmLead.updated_at.desc())
            .limit(1)
        )

    def _attach_call(self, lead: CrmLead, call: Call | None) -> None:
        if call and call.id:
            if not lead.created_from_call_id:
                lead.created_from_call_id = call.id
            lead.last_call_id = call.id

    def _enrich_lead_fields(self, lead: CrmLead, metadata: dict) -> None:
        for field in (
            "interest",
            "industry",
            "use_case",
            "volume",
            "pain_point",
            "budget_range",
            "intent_level",
            "source",
            "campaign",
        ):
            value = metadata.get(field)
            if value and not getattr(lead, field):
                setattr(lead, field, value)
        self._set_correlation_field(lead, "form_submission_id", metadata.get("form_submission_id"))
        self._set_correlation_field(lead, "context_id", metadata.get("context_id"))

    def _set_correlation_field(self, lead: CrmLead, field: str, value: Any) -> None:
        if value in (None, ""):
            return
        incoming = str(value)
        current = getattr(lead, field)
        if not current:
            setattr(lead, field, incoming)
            return
        if current != incoming:
            logger.warning(
                "CRM lead correlation mismatch ignored: lead_id=%s field=%s current=%s incoming=%s",
                lead.id,
                field,
                current,
                incoming,
            )

    def _value(self, data: dict[str, Any] | None, *keys: str) -> str | None:
        if not isinstance(data, dict):
            return None
        for key in keys:
            value = data.get(key)
            if value not in (None, ""):
                return str(value)
        return None
