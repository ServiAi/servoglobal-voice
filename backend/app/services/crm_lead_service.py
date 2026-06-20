from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.crm import CrmLead
from app.services.crm_pipeline_service import CrmPipelineService

class CrmLeadService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.pipeline_service = CrmPipelineService(db)

    def get_or_create_open_lead(
        self,
        tenant_id: str,
        contact_id: str,
        call_id: str | None = None,
        metadata: dict | None = None,
    ) -> CrmLead:
        lead = self.db.scalar(
            select(CrmLead)
            .where(
                CrmLead.tenant_id == tenant_id,
                CrmLead.contact_id == contact_id,
                CrmLead.status == "open",
            )
            .order_by(CrmLead.updated_at.desc())
            .limit(1)
        )

        meta_dict = metadata or {}

        if lead is not None:
            # Update last call if provided
            if call_id:
                lead.last_call_id = call_id

            # Enrich fields if they are empty
            self._enrich_lead_fields(lead, meta_dict)
            self.db.commit()
            self.db.refresh(lead)
        else:
            # Get default pipeline stage
            default_stage = self.pipeline_service.get_stage_by_key(tenant_id, "new")

            # Create new lead
            lead = CrmLead(
                tenant_id=tenant_id,
                contact_id=contact_id,
                current_stage_id=default_stage.id,
                status="open",
                created_from_call_id=call_id,
                last_call_id=call_id,
                interest=meta_dict.get("interest"),
                industry=meta_dict.get("industry"),
                use_case=meta_dict.get("use_case"),
                volume=meta_dict.get("volume"),
                pain_point=meta_dict.get("pain_point"),
                budget_range=meta_dict.get("budget_range"),
                intent_level=meta_dict.get("intent_level"),
                source=meta_dict.get("source"),
                campaign=meta_dict.get("campaign"),
            )
            self.db.add(lead)
            self.db.commit()
            self.db.refresh(lead)

        return lead

    def _enrich_lead_fields(self, lead: CrmLead, metadata: dict) -> None:
        if not lead.interest and metadata.get("interest"):
            lead.interest = metadata.get("interest")
        if not lead.industry and metadata.get("industry"):
            lead.industry = metadata.get("industry")
        if not lead.use_case and metadata.get("use_case"):
            lead.use_case = metadata.get("use_case")
        if not lead.volume and metadata.get("volume"):
            lead.volume = metadata.get("volume")
        if not lead.pain_point and metadata.get("pain_point"):
            lead.pain_point = metadata.get("pain_point")
        if not lead.budget_range and metadata.get("budget_range"):
            lead.budget_range = metadata.get("budget_range")
        if not lead.intent_level and metadata.get("intent_level"):
            lead.intent_level = metadata.get("intent_level")
        if not lead.source and metadata.get("source"):
            lead.source = metadata.get("source")
        if not lead.campaign and metadata.get("campaign"):
            lead.campaign = metadata.get("campaign")
