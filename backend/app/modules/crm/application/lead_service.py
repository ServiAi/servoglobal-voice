from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.crm.application.activity_service import CrmActivityService
from app.modules.crm.application.pipeline_service import CrmPipelineService
from app.modules.crm.application.ports import LeadHistoryPort, SchedulingPort
from app.modules.crm.domain.pipeline import VALID_LEAD_STATUSES
from app.modules.crm.infrastructure.models import CrmContact, CrmLead, CrmVoiceCall


@dataclass(frozen=True)
class _LeadPorts:
    scheduling: SchedulingPort
    history: LeadHistoryPort


class CrmLeadService:
    def __init__(
        self, db: Session, *, scheduling: SchedulingPort | None = None, history: LeadHistoryPort | None = None
    ) -> None:
        self.db = db
        self._scheduling = scheduling
        self._history = history
        self.pipeline_service = CrmPipelineService(db)
        self.activity_service = CrmActivityService(db)

    def _ports(self):
        """Scheduling/history ports (lazy; bound in ``crm.wiring``)."""
        if self._scheduling is None or self._history is None:
            from app.modules.crm.wiring import default_crm_ports

            ports = default_crm_ports(self.db)
            self._scheduling = self._scheduling or ports.scheduling
            self._history = self._history or ports.history
        return _LeadPorts(self._scheduling, self._history)

    def get_or_create_open_lead(
        self,
        tenant_id: str,
        contact_id: str,
        call_id: str | None = None,
        metadata: dict | None = None,
    ) -> CrmLead:
        meta_dict = metadata or {}
        lead = self._open_lead(tenant_id, contact_id)
        if lead is None:
            lead, created = self.claim_or_create_open_lead(
                tenant_id, contact_id, stage_key="new", call_id=call_id, metadata=meta_dict
            )
            if created:
                return lead

        if call_id:
            lead.last_call_id = call_id
        self._enrich_lead_fields(lead, meta_dict)
        self.db.commit()
        self.db.refresh(lead)
        return lead

    def claim_or_create_open_lead(
        self,
        tenant_id: str,
        contact_id: str,
        *,
        stage_key: str = "new",
        call_id: str | None = None,
        metadata: dict | None = None,
        find_existing: Callable[[], CrmLead | None] | None = None,
    ) -> tuple[CrmLead, bool]:
        """THE way to create an open lead: no other application service may build a
        ``CrmLead``. Serialises concurrent requests for the same contact on the
        contact row, re-reads what the caller treats as "the existing lead"
        (``find_existing``; by default the lead correlated by call/context/form or the
        contact's open lead) and creates only when nothing is there. Returns
        ``(lead, created)``; for ``created=False`` the caller enriches the winner.

        The default stages are ensured BEFORE locking (that step commits); there is no
        external I/O under the lock. A unique-index race on call/context/form is
        resolved once by reloading the winner, otherwise re-raised."""
        meta = metadata or {}
        stage = self.pipeline_service.get_stage_by_key(tenant_id, stage_key)
        self.db.execute(
            select(CrmContact.id)
            .where(CrmContact.id == contact_id, CrmContact.tenant_id == tenant_id)
            .with_for_update()
        )
        finder = find_existing or (lambda: self._existing_open_lead(tenant_id, contact_id, call_id, meta))
        existing = finder()
        if existing is not None:
            return existing, False

        lead = CrmLead(
            tenant_id=tenant_id,
            contact_id=contact_id,
            current_stage_id=stage.id,
            status="open",
            created_from_call_id=call_id,
            last_call_id=call_id,
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
        try:
            self.db.commit()
        except IntegrityError:
            # A concurrent request claimed the same call/context/form (partial unique
            # indexes): reload the winner once; no winner means a different failure.
            self.db.rollback()
            winner = finder()
            if winner is None:
                raise
            return winner, False
        self.db.refresh(lead)
        return lead, True

    def _existing_open_lead(
        self, tenant_id: str, contact_id: str, call_id: str | None, meta: dict
    ) -> CrmLead | None:
        for column, value in (
            (CrmLead.created_from_call_id, call_id),
            (CrmLead.context_id, meta.get("context_id") or meta.get("crm_context_id")),
            (CrmLead.form_submission_id, meta.get("form_submission_id") or meta.get("submission_id")),
        ):
            if value:
                found = self.db.scalar(
                    select(CrmLead)
                    .where(CrmLead.tenant_id == tenant_id, column == value)
                    .execution_options(populate_existing=True)
                )
                if found is not None:
                    return found
        return self._open_lead(tenant_id, contact_id)

    def _open_lead(self, tenant_id: str, contact_id: str) -> CrmLead | None:
        return self.db.scalar(
            select(CrmLead)
            .where(
                CrmLead.tenant_id == tenant_id,
                CrmLead.contact_id == contact_id,
                CrmLead.status == "open",
            )
            .order_by(CrmLead.updated_at.desc())
            .limit(1)
            .execution_options(populate_existing=True)
        )

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

    def set_last_call(self, tenant_id: str, lead_id: str, call_id: str) -> None:
        """Point the lead at its most recent call (no commit: the caller's
        transaction decides)."""
        lead = self.get_lead_by_id(tenant_id, lead_id)
        if lead is not None:
            lead.last_call_id = call_id

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
        contact_ids = list(self.db.scalars(select(CrmContact.id).where(CrmContact.tenant_id == tenant_id)))

        # Bookings, WhatsApp messages, voice calls and email sends are
        # operational history outside the lead/contact lifecycle: keep the
        # rows but clear the now-dangling references instead of blocking the
        # delete on their foreign keys. CRM clears its own voice calls; the
        # other modules' rows are cleared through ports.
        self._ports().scheduling.detach_customers(tenant_id=tenant_id, lead_ids=lead_ids, contact_ids=contact_ids)
        self._ports().history.clear_references(tenant_id=tenant_id, lead_ids=lead_ids, contact_ids=contact_ids)
        self.db.execute(
            update(CrmVoiceCall)
            .where(
                CrmVoiceCall.tenant_id == tenant_id,
                or_(CrmVoiceCall.lead_id.in_(lead_ids), CrmVoiceCall.contact_id.in_(contact_ids)),
            )
            .values(lead_id=None, contact_id=None)
        )

        # Form tokens/submissions require a lead and cannot be preserved
        # without one; they are deleted (submissions first, they reference the
        # token) by their owner.
        self._ports().history.delete_form_artifacts(tenant_id=tenant_id, lead_ids=lead_ids)

        for lead in self.db.scalars(select(CrmLead).where(CrmLead.id.in_(lead_ids))):
            self.db.delete(lead)

        # Also delete all contacts for this tenant
        for contact in self.db.scalars(select(CrmContact).where(CrmContact.id.in_(contact_ids))):
            self.db.delete(contact)

        self.db.commit()
        return count

