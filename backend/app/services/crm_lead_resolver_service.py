from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analytics import Call
from app.models.crm import CrmContact, CrmLead
from app.services.crm_pipeline_service import CrmPipelineService


class CrmLeadResolverService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.pipeline_service = CrmPipelineService(db)

    def resolve_existing_lead_for_call(
        self,
        tenant_id: str,
        call: Call,
        contact_id: str | None = None,
    ) -> CrmLead | None:
        if call.id:
            lead = self.db.scalar(
                select(CrmLead)
                .where(
                    CrmLead.tenant_id == tenant_id,
                    CrmLead.created_from_call_id == call.id,
                )
                .limit(1)
            )
            if lead:
                return lead

            lead = self.db.scalar(
                select(CrmLead)
                .where(
                    CrmLead.tenant_id == tenant_id,
                    CrmLead.last_call_id == call.id,
                )
                .order_by(CrmLead.updated_at.desc())
                .limit(1)
            )
            if lead:
                return lead

        if contact_id:
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

        return None

    def resolve_or_create_lead_for_connected_call(
        self,
        tenant_id: str,
        call: Call,
        contact: CrmContact,
        metadata: dict | None = None,
        *,
        stage_key: str = "connected",
    ) -> CrmLead:
        lead = self.resolve_existing_lead_for_call(tenant_id, call, contact.id)
        meta = metadata or {}
        stage = self.pipeline_service.get_stage_by_key(tenant_id, stage_key)

        if lead is None:
            lead = CrmLead(
                tenant_id=tenant_id,
                contact_id=contact.id,
                current_stage_id=stage.id,
                status="open",
                created_from_call_id=call.id,
                last_call_id=call.id,
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

        if call.id:
            if not lead.created_from_call_id:
                lead.created_from_call_id = call.id
            lead.last_call_id = call.id
        self._enrich_lead_fields(lead, meta)
        self.db.commit()
        self.db.refresh(lead)
        return lead

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
