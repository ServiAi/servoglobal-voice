from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.mixins import _uuid
from app.modules.crm.domain.calls import ContextLookup
from app.modules.crm.infrastructure.models import CrmCallContext
from app.modules.crm.domain.contacts import normalize_phone


CONTEXT_PHONE_LOOKBACK_MINUTES = 30


class CrmCallContextService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_context(
        self,
        tenant_id: str,
        *,
        external_provider: str = "ultravox",
        external_call_id: str | None = None,
        context: dict[str, Any] | None = None,
        status: str = "pending",
    ) -> CrmCallContext:
        data = dict(context or {})
        form_submission_id = self._string_value(data, "form_submission_id", "submission_id") or _uuid()
        context_id = self._string_value(data, "context_id", "crm_context_id") or _uuid()
        data["form_submission_id"] = form_submission_id
        data["context_id"] = context_id
        data["crm_context_id"] = context_id
        call_context = CrmCallContext(
            tenant_id=tenant_id,
            external_provider=external_provider,
            external_call_id=external_call_id,
            form_submission_id=form_submission_id,
            context_id=context_id,
            phone=self._string_value(data, "phone", "user_phone", "customer_phone", "lead_phone", "telefono", "celular", "mobile"),
            email=self._string_value(data, "email", "user_email", "customer_email", "lead_email", "correo"),
            name=self._string_value(data, "name", "user_name", "customer_name", "lead_name", "full_name", "nombre"),
            company=self._string_value(data, "company", "company_name", "user_company", "empresa", "organization"),
            interest=self._string_value(data, "interest"),
            industry=self._string_value(data, "industry", "user_industry"),
            use_case=self._string_value(data, "use_case", "user_use_case", "useCase"),
            volume=self._string_value(data, "volume", "user_volume"),
            pain_point=self._string_value(data, "pain_point", "user_pain_point", "painPoint"),
            budget_range=self._string_value(data, "budget_range", "budgetRange"),
            intent_level=self._string_value(data, "intent_level", "intentLevel"),
            source=self._string_value(data, "source"),
            campaign=self._string_value(data, "campaign"),
            utm_source=self._string_value(data, "utm_source"),
            utm_campaign=self._string_value(data, "utm_campaign"),
            raw_context_json=data,
            status=status,
        )
        call_context.phone_normalized = normalize_phone(call_context.phone)
        self.db.add(call_context)
        self.db.commit()
        self.db.refresh(call_context)
        return call_context

    def attach_external_call_id(
        self,
        tenant_id: str,
        context_id: str,
        external_call_id: str,
        *,
        external_provider: str = "ultravox",
    ) -> CrmCallContext | None:
        call_context = self.db.scalar(
            select(CrmCallContext).where(
                CrmCallContext.tenant_id == tenant_id,
                CrmCallContext.id == context_id,
            )
        )
        if call_context is None:
            return None
        call_context.external_provider = external_provider
        call_context.external_call_id = external_call_id
        call_context.status = "attached"
        self.db.commit()
        self.db.refresh(call_context)
        return call_context

    def find_context_for_call(
        self,
        tenant_id: str,
        *,
        external_provider: str = "ultravox",
        external_call_id: str | None = None,
        form_submission_id: str | None = None,
        context_id: str | None = None,
        phone: str | None = None,
    ) -> CrmCallContext | None:
        if external_call_id:
            found = self.db.scalar(
                select(CrmCallContext)
                .where(
                    CrmCallContext.tenant_id == tenant_id,
                    CrmCallContext.external_provider == external_provider,
                    CrmCallContext.external_call_id == external_call_id,
                )
                .order_by(CrmCallContext.created_at.desc())
                .limit(1)
            )
            if found:
                return found

        if form_submission_id:
            found = self.db.scalar(
                select(CrmCallContext)
                .where(
                    CrmCallContext.tenant_id == tenant_id,
                    CrmCallContext.form_submission_id == form_submission_id,
                )
                .order_by(CrmCallContext.created_at.desc())
                .limit(1)
            )
            if found:
                return found

        if context_id:
            found = self.db.scalar(
                select(CrmCallContext)
                .where(
                    CrmCallContext.tenant_id == tenant_id,
                    CrmCallContext.context_id == context_id,
                )
                .order_by(CrmCallContext.created_at.desc())
                .limit(1)
            )
            if found:
                return found

        phone_normalized = normalize_phone(phone)
        if not phone_normalized:
            return None

        since = datetime.now(UTC) - timedelta(minutes=CONTEXT_PHONE_LOOKBACK_MINUTES)
        candidates = list(
            self.db.scalars(
                select(CrmCallContext)
                .where(
                    CrmCallContext.tenant_id == tenant_id,
                    CrmCallContext.phone_normalized == phone_normalized,
                    CrmCallContext.created_at >= since,
                )
                .order_by(CrmCallContext.created_at.desc())
                .limit(2)
            )
        )
        return candidates[0] if len(candidates) == 1 else None

    def find_context_from_lookup(
        self,
        tenant_id: str,
        lookup: ContextLookup,
        *,
        external_provider: str = "ultravox",
    ) -> CrmCallContext | None:
        """Locate the call context a provider payload refers to (the adapter
        turned the payload into ``lookup``; CRM never reads provider payloads)."""
        return self.find_context_for_call(
            tenant_id,
            external_provider=external_provider,
            external_call_id=lookup.external_call_id,
            form_submission_id=lookup.form_submission_id,
            context_id=lookup.context_id,
            phone=lookup.phone,
        )

    def _string_value(self, data: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = data.get(key)
            if value is not None and value != "":
                return str(value)
        return None
