from __future__ import annotations

from datetime import UTC, datetime
from sqlalchemy import select, func, update, delete, or_
from sqlalchemy.orm import Session
from app.models.crm import (
    CrmLead,
    CrmPipelineStage,
    CrmContact,
    CrmBooking,
    CrmWhatsAppMessage,
    CrmVoiceCall,
)
from app.models.integrations import TenantEmailSend, TenantFormSubmission, TenantFormToken
from app.services.crm_pipeline_service import CrmPipelineService
from app.services.crm_activity_service import CrmActivityService


VALID_LEAD_STATUSES = {"open", "won", "lost", "unqualified", "paused"}


class CrmLeadService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.pipeline_service = CrmPipelineService(db)
        self.activity_service = CrmActivityService(db)

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
            if call_id:
                lead.last_call_id = call_id
            self._enrich_lead_fields(lead, meta_dict)
            self.db.commit()
            self.db.refresh(lead)
        else:
            default_stage = self.pipeline_service.get_stage_by_key(tenant_id, "new")
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

    def get_lead_by_id(self, tenant_id: str, lead_id: str) -> CrmLead | None:
        return self.db.scalar(
            select(CrmLead)
            .where(
                CrmLead.tenant_id == tenant_id,
                CrmLead.id == lead_id,
            )
        )

    def update_lead(
        self,
        tenant_id: str,
        lead_id: str,
        **kwargs,
    ) -> CrmLead | None:
        lead = self.get_lead_by_id(tenant_id, lead_id)
        if not lead:
            return None

        if "status" in kwargs and kwargs["status"] is not None:
            if kwargs["status"] not in VALID_LEAD_STATUSES:
                raise ValueError(f"Invalid status: {kwargs['status']}")

        if "lead_score" in kwargs and kwargs["lead_score"] is not None:
            if not (0 <= kwargs["lead_score"] <= 100):
                raise ValueError("lead_score must be between 0 and 100")

        allowed_fields = {
            "interest", "industry", "use_case", "volume", "pain_point",
            "budget_range", "intent_level", "next_action", "lead_score",
            "status", "source", "campaign",
        }

        for key, value in kwargs.items():
            if key in allowed_fields and value is not None:
                setattr(lead, key, value)

        self.db.commit()
        self.db.refresh(lead)

        # Create activity
        self.activity_service.create_activity(
            tenant_id=tenant_id,
            lead_id=lead.id,
            contact_id=lead.contact_id,
            activity_type="lead_updated",
            title="Lead actualizado manualmente",
            description=f"Campos actualizados: {', '.join(k for k in kwargs if k in allowed_fields and kwargs[k] is not None)}",
        )

        return lead

    def change_stage(
        self,
        tenant_id: str,
        lead_id: str,
        stage_key: str,
        reason: str | None = None,
    ) -> CrmLead | None:
        lead = self.get_lead_by_id(tenant_id, lead_id)
        if not lead:
            return None

        # Find target stage
        target_stage = self.pipeline_service.get_stage_by_key(tenant_id, stage_key)
        if not target_stage:
            raise ValueError(f"Stage '{stage_key}' not found for this tenant")

        if target_stage.is_terminal and not (reason and reason.strip()):
            raise ValueError(f"Reason is required when moving to a terminal stage ({stage_key})")

        from_stage_id = lead.current_stage_id
        to_stage_id = target_stage.id

        if from_stage_id == to_stage_id:
            return lead

        lead.current_stage_id = to_stage_id

        # Handle terminal stages
        if target_stage.is_terminal:
            if target_stage.key in ("won",):
                lead.status = "won"
            elif target_stage.key in ("lost", "not_interested"):
                lead.status = "lost"

        self.db.commit()
        self.db.refresh(lead)

        # Create stage change activity with unique dedup key
        timestamp = datetime.now(UTC).isoformat()
        dedup_key = f"manual:{from_stage_id}:{to_stage_id}:{timestamp}"

        self.activity_service.create_activity(
            tenant_id=tenant_id,
            lead_id=lead.id,
            contact_id=lead.contact_id,
            activity_type="stage_changed",
            title=f"Etapa cambiada: {stage_key}",
            description=reason or f"Cambio manual de etapa a {target_stage.name}",
            from_stage_id=from_stage_id,
            to_stage_id=to_stage_id,
            deduplication_key=dedup_key,
        )

        return lead

    def add_note(
        self,
        tenant_id: str,
        lead_id: str,
        note: str,
    ) -> CrmLead | None:
        lead = self.get_lead_by_id(tenant_id, lead_id)
        if not lead:
            return None

        self.activity_service.create_activity(
            tenant_id=tenant_id,
            lead_id=lead.id,
            contact_id=lead.contact_id,
            activity_type="note",
            title="Nota interna",
            description=note,
        )

        return lead

    def delete_lead(self, tenant_id: str, lead_id: str) -> bool:
        lead = self.get_lead_by_id(tenant_id, lead_id)
        if not lead:
            return False

        contact = lead.contact
        self.db.delete(lead)
        self.db.commit()

        # Check if the associated contact has no other leads and delete it if so
        if contact:
            other_leads_count = self.db.scalar(
                select(func.count()).select_from(CrmLead).where(CrmLead.contact_id == contact.id)
            ) or 0
            if other_leads_count == 0:
                self.db.delete(contact)
                self.db.commit()

        return True

    def delete_all_leads(self, tenant_id: str) -> int:
        lead_ids = list(self.db.scalars(select(CrmLead.id).where(CrmLead.tenant_id == tenant_id)))
        count = len(lead_ids)
        if count == 0:
            return 0
        contact_ids = list(self.db.scalars(select(CrmContact.id).where(CrmContact.tenant_id == tenant_id)))

        # Bookings, WhatsApp messages, voice calls and email sends are
        # operational history outside the lead/contact lifecycle: keep the
        # rows but clear the now-dangling references instead of blocking the
        # delete on their foreign keys.
        for model in (CrmBooking, CrmWhatsAppMessage, CrmVoiceCall, TenantEmailSend):
            self.db.execute(
                update(model)
                .where(
                    model.tenant_id == tenant_id,
                    or_(model.lead_id.in_(lead_ids), model.contact_id.in_(contact_ids)),
                )
                .values(lead_id=None, contact_id=None)
            )

        # Form tokens/submissions require a lead and cannot be preserved
        # without one; delete them (submissions first, they reference the
        # token).
        self.db.execute(
            delete(TenantFormSubmission).where(
                TenantFormSubmission.tenant_id == tenant_id,
                TenantFormSubmission.lead_id.in_(lead_ids),
            )
        )
        self.db.execute(
            delete(TenantFormToken).where(
                TenantFormToken.tenant_id == tenant_id,
                TenantFormToken.lead_id.in_(lead_ids),
            )
        )

        for lead in self.db.scalars(select(CrmLead).where(CrmLead.id.in_(lead_ids))):
            self.db.delete(lead)

        # Also delete all contacts for this tenant
        for contact in self.db.scalars(select(CrmContact).where(CrmContact.id.in_(contact_ids))):
            self.db.delete(contact)

        self.db.commit()
        return count

